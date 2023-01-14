import requests

import time
import logging

logger = logging.getLogger(__name__)


class Access:
    """
    This class keep and update access token of Motlin
    Motlin token only works until "self.expires_in" arrives.
    It's bad practise asc token every query, better save queries.
    """

    def __init__(self, client_id, client_secret=None):
        """Init access
        :param client_id: str, internal id of user in motlin
        :param client_secret: str, internal secret code in motlin (if transfer you will get CRUD permissions)
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.expires = 0

        self.access_token = self.get_access_token()

    def get_access_token(self):
        """Get token if it active, else update before get.
        :return: access_token: str, motlin token
        """

        # To be sure that key 100% not expire for example user call before 0.5 sec of expires)
        insurance_period_seconds = 10

        token_work = time.time() < self.expires - insurance_period_seconds

        if token_work:
            return self.access_token

        data = {
            'client_id': self.client_id,
            'grant_type': 'implicit'
        }

        if self.client_secret is not None:
            data['client_secret'] = self.client_secret,
            data['grant_type'] = 'client_credentials'

        response = requests.post('https://api.moltin.com/oauth/access_token', data=data)
        response.raise_for_status()

        access = response.json()

        self.access_token = access['access_token']
        self.expires = access['expires']

        logger.debug('motlin access token was updated')

        return self.access_token


class WrongCustomersNumber(ValueError):
    pass


def get_authorization_headers(access_keeper):
    """Construct headers for next API queries.
    :param access_keeper: object, Access class instance
    :return:
    """
    access_token = access_keeper.get_access_token()
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    return headers


def get_products(access_keeper, category_id=None):
    """Get list of products
    :param access_keeper: object, Access class instance
    :param category_id: str, id of category for filtering
    :return: list of dicts, list of products where product is dict
    """
    logger.debug('getting products...')
    headers = get_authorization_headers(access_keeper)

    filters = None
    if category_id:
        logger.debug(f'filtering by category={category_id}')
        filters = {
            'filter': f'eq(category.id,{category_id})'
        }

    response = requests.get('https://api.moltin.com/v2/products', headers=headers, params=filters)
    response.raise_for_status()

    products = response.json()['data']
    logger.debug(f'{len(products)} products was got')

    return products


def get_all_categories(access_keeper):
    """Get list of categories
    :param access_keeper: object, Access class instance
    :return: list of dicts, list of categories where category is dict
    """
    logger.debug('getting categories...')
    headers = get_authorization_headers(access_keeper)

    response = requests.get('https://api.moltin.com/v2/categories', headers=headers)
    response.raise_for_status()

    categories = response.json()['data']
    logger.debug(f'{len(categories)} categories was got')

    return categories


def get_product_by_id(access_keeper, product_id):
    """Get one product by id (:product_id:).
    :param access_keeper: object, Access class instance
    :param product_id: str, id of product
    :return: dict, product params which recorded in dict
    """
    logger.debug(f'getting product by id: {product_id}...')
    headers = get_authorization_headers(access_keeper)

    response = requests.get(f'https://api.moltin.com/v2/products/{product_id}', headers=headers)
    response.raise_for_status()

    product = response.json()['data']
    logger.debug('product was got')

    return product


def create_product(access_keeper, product):
    """Create new product
    :param access_keeper: object, Access class instance
    :param product: dict, product params which recorded in dict
    :return: str, product id
    """
    logger.debug('create product...')
    headers = get_authorization_headers(access_keeper)

    response = requests.post('https://api.moltin.com/v2/products', headers=headers, json=product)
    response.raise_for_status()

    new_product = response.json()['data']
    product_id = new_product['id']
    logger.debug(f'product with id={product_id} was created')

    return product_id


def get_file_href_by_id(access_keeper, file_id):
    """Get href of file by id (:file_id:).
    :param access_keeper: object, Access class instance
    :param file_id: str, id of file
    :return: str, href
    """
    logger.debug(f'getting href by file id: {file_id}...')
    headers = get_authorization_headers(access_keeper)

    response = requests.get(f'https://api.moltin.com/v2/files/{file_id}', headers=headers)
    response.raise_for_status()

    href = response.json()['data']['link']['href']
    logger.debug('href was got')

    return href


def add_product_to_cart(access_keeper, product_id, quantity, reference):
    """Add :quantity: of product to cart by :produt_id: for :reference: client.
    :param access_keeper: object, Access class instance
    :param product_id: str, id of product
    :param quantity: str or int, quantity of product (in pcs)
    :param reference: str, some internal string-ID of the client that is used to search for the cart in the future
    :return: dict, response of API
    """
    logger.debug(f'adding product {product_id} in cart. quantity: {quantity}. reference: {reference}...')
    headers = get_authorization_headers(access_keeper)
    headers['Content-Type'] = 'application/json'

    data = {
        'data':
            {
                'id': product_id,
                'type': 'cart_item',
                'quantity': int(quantity)  # if not int API return 400
            }
    }

    response = requests.post(f'https://api.moltin.com/v2/carts/{reference}/items', headers=headers, json=data)
    response.raise_for_status()
    logger.debug('product was added')

    return response.json()


def get_cart_items_info(access_keeper, reference):
    """Get all product in cart for :reference:.
    :param access_keeper: object, Access class instance
    :param reference: str, some internal string-ID of the client that is used to search for the cart in the future
    :return: dict, keys 'products' (value list of dict with product params) and 'total_price' (value string with formatted price)
    """
    logger.debug(f'getting cart items. reference - {reference}...')
    headers = get_authorization_headers(access_keeper)

    response = requests.get(f'https://api.moltin.com/v2/carts/{reference}/items', headers=headers)
    response.raise_for_status()
    logger.debug('cart items were got')

    items_in_cart = response.json()['data']
    response_meta = response.json()['meta']

    logger.debug(f'{len(items_in_cart)} items in cart')

    items_in_cart_for_response = {'products': []}
    for item in items_in_cart:
        item_in_cart = {
            'description': item['description'],
            'name': item['name'],
            'quantity': item['quantity'],
            'price_per_unit': item['meta']['display_price']['with_tax']['unit']['formatted'],
            'total_price': item['meta']['display_price']['with_tax']['value']['formatted'],
            'product_id': item['product_id'],
            'cart_item_id': item['id']
        }
        items_in_cart_for_response['products'].append(item_in_cart)
        logger.debug(f'item {item["id"]} was handled')

    total_price = response_meta['display_price']['with_tax']['formatted']
    total_price_amount = response_meta['display_price']['with_tax']['amount']
    items_in_cart_for_response['total_price'] = total_price
    items_in_cart_for_response['total_price_amount'] = total_price_amount

    logger.debug('items in carts were handled')

    return items_in_cart_for_response


def delete_cart_item(access_keeper, reference, cart_item_id):
    """Delete product from :reference: cart by :cart_item_id:
    :param access_keeper: object, Access class instance
    :param reference: str, some internal string-ID of the client that is used to search for the cart in the future
    :param cart_item_id: str, id of item in cart
    :return: dict, response of API
    """
    logger.debug(f'delete cart item {cart_item_id}...')
    headers = get_authorization_headers(access_keeper)

    response = requests.delete(f'https://api.moltin.com/v2/carts/{reference}/items/{cart_item_id}', headers=headers)
    response.raise_for_status()
    logger.debug(f'cart item {cart_item_id} was deleted')

    return response.json()


def get_customer_id_by_name_and_email(access_keeper, customer_email, customer_name):
    """Get customer filtered by name and email.
    :param access_keeper: object, Access class instance
    :param customer_email: str, email of customer
    :param customer_name: str, name of customer
    :return: str, id of customer
    """
    logger.debug(f'getting customer by email: {customer_email} and name {customer_name}...')
    headers = get_authorization_headers(access_keeper)

    # motlin filtering - https://documentation.elasticpath.com/commerce-cloud/docs/api/basics/filtering.html
    params = {
        'filter': f'eq(name,{customer_name}):eq(email,{customer_email})'
    }
    response = requests.get('https://api.moltin.com/v2/customers', headers=headers, params=params)
    response.raise_for_status()

    customers = response.json()['data']
    logger.debug('customers was got')

    if len(customers) != 1:
        raise WrongCustomersNumber(f'Waiting 1 customer but got {len(customers)}')

    customer_id = customers[0]['id']

    return customer_id


def create_customer(access_keeper, name, email):
    """Create a new customer with name-:name: and email-:email:.
    If the client exists, the status code 409 will be returned.
    If the name or email address is incorrect, status code 422 will be returned.
    Else result in json will be returned.
    :param access_keeper: object, Access class instance
    :param name: str, name of client, not Null
    :param email: str, email of client, should be valid (elasticpath API will check)
    :return: dict or int, info about creation or status code
    """
    logger.debug(f'Creating customer {name} with email {email}...')
    headers = get_authorization_headers(access_keeper)
    headers['Content-Type'] = 'application/json'

    data = {
        'data': {
            'type': 'customer',
            'name': name,
            'email': email
        }
    }

    response = requests.post('https://api.moltin.com/v2/customers', headers=headers, json=data)
    if response.status_code not in [409, 422]:
        response.raise_for_status()
        logger.debug('customer was added')
        return response.json()

    return response.status_code


def upload_image(access_keeper, image_url):
    """Upload image to cms
    :param access_keeper: object, Access class instance
    :param image_url: str, url of image
    :return: str, image id
    """
    logger.debug('upload image...')
    headers = get_authorization_headers(access_keeper)

    files = {
        'file_location': (None, image_url),
    }

    response = requests.post('https://api.moltin.com/v2/files', headers=headers, files=files)
    response.raise_for_status()

    image = response.json()['data']
    image_id = image['id']
    logger.debug(f'image with id={image_id} was uploaded')

    return image_id


def upload_image_to_product(access_keeper, product_id, image_url):
    """Link product and image
    :param access_keeper: object, Access class instance
    :param product_id: str, id of product
    :param image_url: str, url of image
    :return: str, image id
    """
    logger.debug('link product and image...')
    headers = get_authorization_headers(access_keeper)

    image_id = upload_image(access_keeper, image_url)

    data = {
        'data': {
            'type': 'main_image',
            'id': image_id,
        },
    }

    url = f'https://api.moltin.com/v2/products/{product_id}/relationships/main-image'
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()

    logger.debug(f'image with id={image_id} was linked with product with id={product_id}')

    return image_id


def create_flow(access_keeper, flow):
    """Create a new flow.
    :param access_keeper: object, Access class instance
    :param flow: dict, flow data with name, description, slug, etc...
    :return: int, id of created flow
    """
    logger.debug('creating flow...')
    headers = get_authorization_headers(access_keeper)
    headers['Content-Type'] = 'application/json'

    response = requests.post('https://api.moltin.com/v2/flows', headers=headers, json=flow)
    response.raise_for_status()

    new_flow = response.json()['data']
    flow_id = new_flow['id']
    logger.debug(f'flow with id={flow_id} was created')

    return flow_id


def create_field(access_keeper, field):
    """Create a new filed linked with flow.
    :param access_keeper: object, Access class instance
    :param field: dict, field data with params and flow relationship
    :return: int, id of created field
    """
    flow_id = field['data']['relationships']['flow']['data']['id']
    logger.debug(f'creating field, flow_id={flow_id}...')
    headers = get_authorization_headers(access_keeper)
    headers['Content-Type'] = 'application/json'

    response = requests.post('https://api.moltin.com/v2/fields', headers=headers, json=field)
    response.raise_for_status()

    new_field = response.json()['data']
    field_id = new_field['id']
    logger.debug(f'field with id={field_id} was created')

    return field_id


def upload_entry_to_flow(access_keeper, entry, flow_slug):
    """Create a new entry in flow.
    :param access_keeper: object, Access class instance
    :param entry: dict, entry data with params
    :param flow_slug: str, the slug of flow into which entry is loaded
    :return: int, id of created entry
    """
    logger.debug(f'upload entry to flow with slug={flow_slug}...')
    headers = get_authorization_headers(access_keeper)
    headers['Content-Type'] = 'application/json'

    response = requests.post(f'https://api.moltin.com/v2/flows/{flow_slug}/entries', headers=headers, json=entry)
    response.raise_for_status()

    new_entry = response.json()['data']
    entry_id = new_entry['id']
    logger.debug(f'entry with id={entry_id} was created')

    return entry_id


def get_all_entries_of_flow(access_keeper, flow_slug):
    """Get list of entries
    :param access_keeper: object, Access class instance
    :param flow_slug: str, slug of flow
    :return: list of dicts, list of entries where entry is dict
    """
    logger.debug('getting entries...')
    headers = get_authorization_headers(access_keeper)

    response = requests.get(f'https://api.moltin.com/v2/flows/{flow_slug}/entries', headers=headers)
    response.raise_for_status()

    entries = response.json()['data']
    logger.debug(f'{len(entries)} entries was got')

    return entries


def create_integration(access_keeper, webhook_url):
    """Add webhook integration with motlin
    :param access_keeper: object, Access class instance
    :param webhook_url: str, url of server which will get information from motlin
    """
    logger.debug('creating webhook integration...')
    headers = get_authorization_headers(access_keeper)
    headers['Content-Type'] = 'application/json'

    integration = {
        "data": {
            "type": "integration",
            "name": "Product notification",
            "description": "Send notification about products manipulations.",
            "enabled": True,
            "observes": [
                "product.created",
                "product.updated",
                "product.deleted",
            ],
            "integration_type": "webhook",
            "configuration": {
                "url": webhook_url,
                "secret_key": access_keeper.client_secret
            }
        }
    }

    response = requests.post('https://api.moltin.com/v2/integrations', headers=headers, json=integration)
    response.raise_for_status()

    logger.debug('webhook integration created...')
