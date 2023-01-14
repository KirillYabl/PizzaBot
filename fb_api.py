import json
import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


def send_message(token: str, recipient_id: str, message_text: str) -> None:
    """Send message"""
    logger.debug('sending message...')
    params = {"access_token": token}
    headers = {"Content-Type": "application/json"}
    message = json.dumps({
        "recipient": {
            "id": recipient_id
        },
        "message": {
            "text": message_text
        }
    })
    response = requests.post("https://graph.facebook.com/v2.6/me/messages", params=params, headers=headers,
                             data=message)
    response.raise_for_status()
    logger.debug('message sent')


def send_carousel_buttons(token: str, recipient_id: str, elements: list[dict[str, Any]]) -> None:
    """Send carousel buttons"""
    logger.debug('sending buttons...')
    params = {"access_token": token}
    headers = {'Content-Type': 'application/json'}

    carousel = json.dumps({
        'recipient': {
            'id': recipient_id,
        },
        'message': {
            'attachment': {
                'type': 'template',
                'payload': {
                    'template_type': 'generic',
                    'elements': elements,
                },
            },
        },
    })

    response = requests.post('https://graph.facebook.com/v2.6/me/messages',
                             headers=headers, data=carousel, params=params)
    response.raise_for_status()
    logger.debug('buttons sent')
