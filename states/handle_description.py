import logging

import motlin_api
import telegram

from common_functions import get_motlin_access_keeper, get_chat_id, send_cart_info
from states.start import start

logger = logging.getLogger(__name__)

# for typing
ContextType = telegram.ext.callbackcontext.CallbackContext
UpdateType = telegram.update.Update


def handle_description(update: UpdateType, context: ContextType) -> str:
    """Product description menu."""
    bot = context.bot
    chat_id = get_chat_id(update)
    query = update.callback_query
    if query.data == 'back_to_products':
        logger.debug('User chose return to products')
        condition = start(update, context)
        return condition

    if query.data == 'cart':
        logger.debug('User chose watch the cart')
        condition = send_cart_info(context, update)
        return condition

    access_keeper = get_motlin_access_keeper()
    product_id, quantity = query.data.split()
    logger.debug(f'User chose add product to cart. Product_id = {product_id}; quantity={quantity}')
    motlin_api.add_product_to_cart(access_keeper, product_id, quantity, chat_id)
    update.callback_query.answer('Добавлено в корзину')
    return 'HANDLE_DESCRIPTION'
