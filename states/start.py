import logging
import math

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext.callbackcontext import CallbackContext
from telegram.update import Update

import motlin_api

logger = logging.getLogger(__name__)


def start(update: Update, context: CallbackContext, page_number: int = 1) -> str:
    """Bot /start command."""
    bot = context.bot
    products = motlin_api.get_products(context.bot_data['access_keeper'])
    chat_id = update.effective_chat.id
    cart_items_info = motlin_api.get_cart_items_info(context.bot_data['access_keeper'], chat_id)
    products_in_cart = {product['product_id']: product for product in cart_items_info['products']}

    keyboard = []
    products_on_page = context.bot_data['config']['products_on_page']
    logger.debug(f'page_number = {page_number}')

    start_product_index = (page_number - 1) * products_on_page
    end_product_index = page_number * products_on_page
    for product in products[start_product_index:end_product_index]:
        product_name = product['name']
        product_id = product['id']

        product_in_cart = products_in_cart.get(product_id, None)
        msg = product_name
        if product_in_cart:
            msg = f'{product_name} ({product_in_cart["quantity"]} шт. в корзине)'

        btn = InlineKeyboardButton(msg, callback_data=product_id)

        keyboard.append([btn])
        logger.debug(f'product {product_name} was added to keyboard. Product id: {product_id}')

    first_page_number = 1
    pages = [first_page_number]
    if len(products) > products_on_page:
        pages_count = math.ceil(len(products) / products_on_page)
        last_page_number = pages_count + 1
        pages = [i for i in range(first_page_number, last_page_number)]

    next_page_number = page_number + 1
    prev_page_number = page_number - 1
    next_page_button = InlineKeyboardButton('>>', callback_data=f'page-{next_page_number}')
    prev_page_button = InlineKeyboardButton('<<', callback_data=f'page-{prev_page_number}')

    last_page_number = pages[-1]
    has_other_pages = len(pages) > 1
    if page_number == first_page_number and has_other_pages:
        keyboard.append([next_page_button])
    elif page_number == last_page_number and has_other_pages:
        keyboard.append([prev_page_button])
    elif has_other_pages:
        keyboard.append([prev_page_button, next_page_button])

    keyboard.append([InlineKeyboardButton('Корзина', callback_data='cart')])

    reply_markup = InlineKeyboardMarkup(keyboard)
    logger.debug('keyboard was constructed')

    bot.send_message(text='Выберите продукт', reply_markup=reply_markup, chat_id=chat_id)

    return 'HANDLE_MENU'
