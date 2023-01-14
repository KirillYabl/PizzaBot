import enum
import json
import logging
from typing import Any

import environs
from flask import Flask, request
from redis import Redis

import fb_api
import motlin_api

logger = logging.getLogger(__name__)
app = Flask(__name__)


class EventType(enum.Enum):
    MESSAGE = 'MESSAGE'
    POSTBACK = 'POSTBACK'


@app.route('/', methods=['GET'])
def verify() -> tuple[str, int]:
    """
    При верификации вебхука у Facebook он отправит запрос на этот адрес. На него нужно ответить VERIFY_TOKEN.
    """
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.challenge"):
        if not request.args.get("hub.verify_token") == env.str("FB_VERIFY_TOKEN"):
            return "Verification token mismatch", 403
        return request.args["hub.challenge"], 200

    return "Hello world", 200


def get_menu_by_category(category_id: str, categories: list[dict[str, Any]], pizza_logo_url: str,
                         pizza_categories_url: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
    max_products_on_page = 10
    extra_elements = 2  # manage element and categories element
    max_buttons_for_element = 3
    access_keeper = get_access_keeper()
    pizzas = motlin_api.get_products(access_keeper, category_id)[:max_products_on_page - extra_elements]
    pizzas_buttons = [
        {
            'title': f'{pizza["name"]} ({pizza["meta"]["display_price"]["with_tax"]["formatted"]})',
            'subtitle': pizza['description'],
            'image_url': motlin_api.get_file_href_by_id(
                access_keeper,
                pizza['relationships']['main_image']['data']['id']
            ),
            'buttons': [{
                'type': 'postback',
                'title': 'Добавить в корзину',
                'payload': f'ADD_TO_CART:{pizza["id"]}'
            }]
        }
        for pizza in pizzas
    ]
    image_urls = {
        pizza_button['buttons'][0]['payload'].split('ADD_TO_CART:')[-1]: pizza_button['image_url']
        for pizza_button in pizzas_buttons
    }
    elements = \
        [
            {
                'title': 'Меню',
                'subtitle': 'Добавьте пиццы в корзину и сделайте заказ',
                'image_url': pizza_logo_url,
                'buttons': [
                    {
                        'type': 'postback',
                        'title': 'Корзина',
                        'payload': 'CART'
                    },
                    {
                        'type': 'postback',
                        'title': 'Сделать заказ',
                        'payload': 'ORDER'
                    }
                ]
            }
        ] + pizzas_buttons + [
            {
                'title': 'Не нашли нужную пиццу?',
                'subtitle': 'Остальные пиццы можно посмотреть в одной из категорий',
                'image_url': pizza_categories_url,
                'buttons': [
                               {
                                   'type': 'postback',
                                   'title': other_category['name'],
                                   'payload': f'CATEGORY_ID:{other_category["id"]}'
                               }
                               for other_category
                               in [category for category in categories if category['id'] != category_id]
                           ][:max_buttons_for_element - 1]
            }
        ]
    return elements, image_urls


def handle_start(sender_id: str, message_text: str, event_type: EventType) -> str:
    logger.debug('start...')
    db = get_db_conn()
    access_keeper = get_access_keeper()
    category_id = env.str('MAIN_CATEGORY_ID', None)
    if event_type == EventType.POSTBACK:
        if message_text.startswith('CATEGORY_ID:'):
            category_id = message_text.split('CATEGORY_ID:')[1]
        else:
            category_id = env.str('MAIN_CATEGORY_ID', None)

    elements = db.get(f'menu:{category_id}')
    if not elements:
        categories = motlin_api.get_all_categories(access_keeper)
        elements, image_urls = get_menu_by_category(category_id, categories, env.str('PIZZA_LOGO_URL'),
                                                    env.str('PIZZA_CATEGORIES_URL'))
        db.set(f'menu:{category_id}', json.dumps(elements))
    else:
        elements = json.loads(elements.decode('utf-8'))

    fb_api.send_carousel_buttons(env.str("FB_PAGE_ACCESS_TOKEN"), sender_id, elements)
    logger.debug('menu showed')
    return 'MENU'


def construct_cart(sender_id: str, cart_image_url: str) -> list[dict[str, Any]]:
    db = get_db_conn()
    access_keeper = get_access_keeper()
    cart_items_info = motlin_api.get_cart_items_info(access_keeper, sender_id)
    images = db.get('pizza_images')
    if images:
        images = json.loads(images)
    else:
        images = {}

    total_price = cart_items_info['total_price']
    cart_elements = \
        [
            {
                'title': 'Корзина',
                'subtitle': f'Ваш заказ на сумму {total_price}',
                'image_url': cart_image_url,
                'buttons': [
                    {
                        'type': 'postback',
                        'title': 'Самовывоз',
                        'payload': 'PICKUP'
                    },
                    {
                        'type': 'postback',
                        'title': 'Доставка',
                        'payload': 'DELIVERY'
                    },
                    {
                        'type': 'postback',
                        'title': 'К меню',
                        'payload': 'MENU'
                    }
                ]
            }
        ] + [
            {
                'title': f'{item["name"]} ({item["quantity"]} шт.)',
                'subtitle': item['description'],
                'image_url': images.get(item["product_id"], '') or motlin_api.get_file_href_by_id(
                    access_keeper,
                    motlin_api.get_product_by_id(
                        access_keeper,
                        item["product_id"]
                    )['relationships']['main_image']['data']['id']
                ),
                'buttons': [
                    {
                        'type': 'postback',
                        'title': 'Добавить еще одну',
                        'payload': f'ADD_TO_CART_ONE_MORE:{item["product_id"]}'
                    },
                    {
                        'type': 'postback',
                        'title': 'Убрать из корзины',
                        'payload': f'REMOVE_FROM_CART:{item["cart_item_id"]}'
                    }
                ]
            }
            for item in cart_items_info['products']
        ]
    return cart_elements


def handle_menu(sender_id: str, message_text: str, event_type: EventType) -> str:
    logger.debug('menu...')
    access_keeper = get_access_keeper()
    if event_type == EventType.POSTBACK:
        logger.debug('get postback')
        if message_text.startswith('ADD_TO_CART:'):
            logger.debug('add to cart from start')
            product_id = message_text.split('ADD_TO_CART:')[1]
            quantity = 1
            motlin_api.add_product_to_cart(access_keeper, product_id, quantity, sender_id)
            condition = handle_start(sender_id, message_text, event_type)
            return condition
        elif message_text.startswith('ADD_TO_CART_ONE_MORE:'):
            logger.debug('add to cart from cart')
            product_id = message_text.split('ADD_TO_CART_ONE_MORE:')[1]
            quantity = 1
            motlin_api.add_product_to_cart(access_keeper, product_id, quantity, sender_id)
            elements = construct_cart(sender_id, env.str('CART_IMAGE_URL'))
        elif message_text == 'CART':
            logger.debug('show cart')
            elements = construct_cart(sender_id, env.str('CART_IMAGE_URL'))
        elif message_text.startswith('REMOVE_FROM_CART:'):
            logger.debug('remove from cart')
            cart_item_id = message_text.split('REMOVE_FROM_CART:')[1]
            motlin_api.delete_cart_item(access_keeper, sender_id, cart_item_id)
            elements = construct_cart(sender_id, env.str('CART_IMAGE_URL'))
        elif message_text == 'MENU':
            condition = handle_start(sender_id, message_text, event_type)
            return condition
        fb_api.send_carousel_buttons(env.str("FB_PAGE_ACCESS_TOKEN"), sender_id, elements)
    return 'MENU'


def handle_users_reply(sender_id: str, message_text: str, event_type: EventType) -> None:
    states_functions = {
        'START': handle_start,
        'MENU': handle_menu,
    }
    db = get_db_conn()
    recorded_state = db.get(f'facebookid_{sender_id}')
    if not recorded_state or recorded_state.decode("utf-8") not in states_functions.keys():
        user_state = "START"
    else:
        user_state = recorded_state.decode("utf-8")
    if message_text == "/start":
        user_state = "START"
    state_handler = states_functions[user_state]
    next_state = state_handler(sender_id, message_text, event_type)
    db.set(f'facebookid_{sender_id}', next_state)


@app.route('/', methods=['POST'])
def webhook() -> tuple[str, int]:
    """
    Основной вебхук, на который будут приходить сообщения от Facebook.
    """
    logger.debug('webhook...')
    data = request.get_json()

    if "object" in data and data["object"] == "page":  # facebook webhook
        logger.debug('facebook')
        for entry in data["entry"]:
            for messaging_event in entry["messaging"]:
                if messaging_event.get("message"):  # someone sent us a message
                    logger.debug('get message')
                    sender_id = messaging_event["sender"]["id"]  # the facebook ID of the person sending you the message
                    recipient_id = messaging_event["recipient"][
                        "id"]  # the recipient's ID, which should be your page's facebook ID
                    message_text = messaging_event["message"]["text"]  # the message's text
                    handle_users_reply(sender_id, message_text, EventType.MESSAGE)
                elif messaging_event.get("postback"):  # someone sent us a message
                    logger.debug('get postback')
                    sender_id = messaging_event["sender"]["id"]  # the facebook ID of the person sending you the message
                    recipient_id = messaging_event["recipient"][
                        "id"]  # the recipient's ID, which should be your page's facebook ID
                    payload = messaging_event["postback"]["payload"]  # the message's text
                    handle_users_reply(sender_id, payload, EventType.POSTBACK)
    elif data.get('configuration', {}).get('secret_key', '') == env.str('MOTLIN_CLIENT_SECRET'):  # motlin webhook
        logger.debug('motlin')
        db = get_db_conn()
        access_keeper = get_access_keeper()
        categories = motlin_api.get_all_categories(access_keeper)
        images = {}
        for pizza_category in categories:
            elements, image_urls = get_menu_by_category(pizza_category['id'], categories, env.str('PIZZA_LOGO_URL'),
                                                        env.str('PIZZA_CATEGORIES_URL'))
            images.update(image_urls)
            db.set(f'menu:{pizza_category["id"]}', json.dumps(elements))
        db.set('pizza_images', json.dumps(images))
        logger.debug('cache updated')
    return "ok", 200


def get_db_conn() -> Redis:
    global db
    if not db:
        db = Redis(
            host=env.str('REDIS_DB_ADDRESS'),
            port=env.int('REDIS_DB_PORT'),
            password=env.str('REDIS_DB_PASSWORD')
        )
    return db


def get_access_keeper() -> motlin_api.Access:
    global access_keeper
    if not access_keeper:
        access_keeper = motlin_api.Access(env.str('MOTLIN_CLIENT_ID'), env.str('MOTLIN_CLIENT_SECRET'))
    return access_keeper


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    env = environs.Env()
    env.read_env()
    app.run(debug=True)
