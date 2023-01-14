import environs
import logging
from typing import Optional, Dict, Any

from redis import Redis
from telegram.ext import Updater
from telegram.ext import Filters
from telegram.ext import PreCheckoutQueryHandler
from telegram.ext import CommandHandler
from telegram.ext import CallbackQueryHandler
from telegram.ext import MessageHandler
from telegram.ext.callbackcontext import CallbackContext
from telegram.update import Update

from motlin_api import Access
from states.handle_cart import handle_cart
from states.handle_description import handle_description
from states.handle_menu import handle_menu
from states.start import start
from states.waiting_delivery_type import waiting_delivery_type
from states.waiting_email import waiting_email
from states.waiting_geo import waiting_geo

logger = logging.getLogger(__name__)


def successful_payment_callback(update: Update, context: CallbackContext) -> None:
    update.message.reply_text("Thank you for your payment!")
    context.user_data['succesful_callback']()
    del context.user_data['succesful_callback']

    msg = 'Отправьте команду /start если хотите сделать новый заказ'
    bot = context.bot
    chat_id = update.effective_chat.id
    bot.send_message(text=msg, chat_id=chat_id)


def precheckout_callback(update: Update, context: CallbackContext) -> Optional[str]:
    query = update.pre_checkout_query
    if 'succesful_callback' not in context.user_data or not context.user_data['succesful_callback']:
        logger.warning('Can not find succesful_callback')
        msg = 'Что-то пошло не так, пожалуйста, попробуйте снова сделать заказ'
        context.bot.answer_pre_checkout_query(pre_checkout_query_id=query.id, ok=False, error_message=msg)
        condition = start(update, context)
        return condition
    context.bot.answer_pre_checkout_query(pre_checkout_query_id=query.id, ok=True)


def handle_users_reply(update: Update, context: CallbackContext) -> None:
    """Bot's state machine."""

    if update.message:
        user_reply = update.message.text
        chat_id = update.message.chat_id
    elif update.callback_query:
        user_reply = update.callback_query.data
        chat_id = update.callback_query.message.chat_id
    else:
        return

    if user_reply == '/start':
        user_state = 'START'
        context.bot_data['db'].set(f'telegramid_{chat_id}', user_state)
    else:
        user_state = context.bot_data['db'].get(chat_id).decode("utf-8")

    logger.debug(f'User state: {user_state}')

    states_functions = {
        'START': start,
        'HANDLE_MENU': handle_menu,
        'HANDLE_DESCRIPTION': handle_description,
        'HANDLE_CART': handle_cart,
        'WAITING_EMAIL': waiting_email,
        'WAITING_GEO': waiting_geo,
        'WAITING_DELIVERY_TYPE': waiting_delivery_type
    }
    state_handler = states_functions[user_state]
    next_state = state_handler(update, context)
    context.bot_data['db'].set(f'telegramid_{chat_id}', next_state)


def error(update: Update, context: CallbackContext) -> None:
    """Log Errors caused by Updates."""
    logger.warning(f'Update "{update}" caused error "{context.error}"')


def get_config() -> Dict[str, Any]:
    """Get config."""
    config = {
        'tg_bot_token': env.str('TG_BOT_TOKEN'),
        'proxy': env.str('PROXY', None),
        'motlin_client_id': env.str("MOTLIN_CLIENT_ID"),
        'motlin_client_secret': env.str("MOTLIN_CLIENT_SECRET", None),
        'redis_db_password': env.str("REDIS_DB_PASSWORD"),
        'redis_db_address': env.str("REDIS_DB_ADDRESS"),
        'redis_db_port': env.int("REDIS_DB_PORT"),
        'products_on_page': env.int("PRODUCTS_ON_PAGE", 8),
        'yandex_geo_apikey': env.str("YANDEX_GEO_APIKEY"),
        'pizzeria_addresses_flow_slug': env.str("PIZZERIA_ADDRESSES_FLOW_SLUG", "pizzeria-addresses"),
        'customer_addresses_flow_slug': env.str("CUSTOMER_ADDRESSES_FLOW_SLUG", "customer-addresses"),
        'customer_addresses_customer_id_slug': env.str("CUSTOMER_ADDRESSES_CUSTOMER_ID_SLUG",
                                                       "customer-addresses-customer-id"),
        'customer_addresses_longitude_slug': env.str("CUSTOMER_ADDRESSES_LONGITUDE_SLUG",
                                                     "customer-addresses-longitude"),
        'customer_addresses_latitude_slug': env.str("CUSTOMER_ADDRESSES_LATITUDE_SLUG",
                                                    "customer-addresses-latitude"),
        'pizzeria_addresses_deliveryman_telegram_chat_id': env.str("PIZZERIA_ADDRESSES_DELIVERYMAN_TELEGRAM_CHAT_ID",
                                                                   "pizzeria-addresses-deliveryman-telegram-chat-id"),
        'pizzeria_addresses_address': env.str("PIZZERIA_ADDRESSES_ADDRESS", "pizzeria-addresses-address"),
        'bank_token': env.str("BANK_TOKEN")
    }

    logger.debug('.env was read, config was constructed')

    return config


def main():
    logging.basicConfig(format='%(asctime)s  %(name)s  %(levelname)s  %(message)s', level=logging.DEBUG)

    config = get_config()

    request_kwargs = None
    if config['proxy']:
        request_kwargs = {'proxy_url': config['proxy']}
        logger.debug(f'Using proxy - {config["proxy"]}')
    updater = Updater(
        token=config['tg_bot_token'],
        use_context=True,
        request_kwargs=request_kwargs,
    )
    logger.debug('Connection with TG was established')

    updater.dispatcher.add_handler(CallbackQueryHandler(handle_users_reply))
    updater.dispatcher.add_handler(MessageHandler(Filters.text, handle_users_reply))
    updater.dispatcher.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    updater.dispatcher.add_handler(MessageHandler(Filters.successful_payment, successful_payment_callback))
    updater.dispatcher.add_handler(CommandHandler('start', start))
    updater.dispatcher.add_error_handler(error)

    # can't use telegram Persistence classes because they don't support classes
    config = get_config()
    updater.dispatcher.bot_data['config'] = config
    access_keeper = Access(config['motlin_client_id'], config['motlin_client_secret'])

    db = Redis(
        host=config['redis_db_address'],
        port=config['redis_db_port'],
        password=config['redis_db_password']
    )

    updater.dispatcher.bot_data['access_keeper'] = access_keeper
    updater.dispatcher.bot_data['db'] = db

    updater.start_polling()

    # need to job queue work
    # https://stackoverflow.com/questions/70673175/runtimeerror-cannot-schedule-new-futures-after-interpreter-shutdown/70722653#70722653
    updater.idle()


if __name__ == '__main__':
    env = environs.Env()
    env.read_env()
    main()
