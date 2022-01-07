# import concurrent
import json
import random
import time
import sys
# from concurrent.futures import ProcessPoolExecutor
# from multiprocessing.pool import Pool
# from pprint import pprint

import cfscrape
import requests
from bs4 import BeautifulSoup

from config import proxies_file, delay, delay_check_product, keywords, new_product_region, n_keywords, URLS, PRODUCTS, queries
from config import discord_url as WEBHOOK
from config import slack_url as SLACK_WEBHOOK
from webhook import Webhook
from agents import AGENTS


global bad_proxies
bad_proxies = []


def open_proxies():
    with open(proxies_file, 'r') as f:
        return f.read().split('\n')


def load_data(file):
    with open(file) as f:
        return json.load(f)


def save_new_data(data, file):
    with open(file, 'w') as fp:
        json.dump(data, fp, indent=4)


def make_request(url, prxs, s, retry=0):
    if retry > 3:
        return None
    px = random.choice(prxs)
    headers = {"User-Agent": random.choice(AGENTS)}
    proxies = {"http": "http://{}".format(px)}
    r = requests.get(url=url, proxies=proxies, headers=headers)


    if r.status_code != 200:
        if r.status_code == 404:
            print(r.status_code, url)
            return 404
        print(r.status_code, url)
    if r.status_code == 403:
        retry += 1
        print("Failed request for {}".format(url))
        return make_request(url, prxs, s, retry)
    elif "/429.php" in r.url:
        print("429 Page for {}".format(url))
    else:
        print('Succesfull request for {}'.format(url))
    return r


def send_embed(product):
    sizes = []

    for id, size in zip(product['atc'], product['sizes']):
        atc = "https://www.solebox.com/index.php?aid={0}&anid={0}&parentid={0}&panid=&fnc=tobasket&am=1".format(id)
        siz = size.strip().replace('\n', '')
        sizes.append("{} [[Add To Cart]]({})".format(siz, atc))

    sizes2 = None
    embed = Webhook(WEBHOOK, color=123123)

    embed.set_title(title=product['name'],
                    url=product['url'])
    #embed.set_desc("** {} **".format(desc))

    if product['price']:
        embed.add_field(name='Price',
                        value=product['price'],
                        inline=True)

    if product['status']:
        embed.add_field(name='Status',
                        value=product['status'].capitalize(),
                        inline=True)


    if product['image']:
        embed.set_thumbnail(product['image'])

    embed.add_field(name='Shop',
                    value='[WellGosh](https://wellgosh.com)',
                    inline=True)

    embed.set_footer(text="Bentley Monitor", ts=True)

    # if sizes:
    #     sizes2 = None
    #     if len(sizes) > 9:
    #         sizes2 = sizes[9:]
    #         sizes = sizes[:9]

    #     embed.add_field(name='Sizes',
    #                     value='\n'.join(sizes),
    #                     inline=False)
    # if sizes2:
    #     embed.add_field(name='Sizes',
    #                     value='\n'.join(sizes2),
    #                     inline=False)
    embed.post()

def send_embed_s(product):
    sizes = '\n'.join(product['sizes'])
    payload = {
        "attachments": [
            {"text": "Supreme Restock",
             "fallback": "Restock",
             "color": "#36a64f",
             "title": product['name'],
             "title_link": product['url'],
             "fields": [
                 {
                     "title": "Price:",
                     "value": product['price'],
                     "short": False
                 },
                 {
                     'title': "Size/ATC:",
                     'value': sizes if sizes else "-",
                     "short": False
                 }
             ],
             #
             }
        ]
    }
    if product['image']:
        payload['attachments'][0]['thumb_url'] = product['image']
    response = requests.post(SLACK_WEBHOOK, data=json.dumps(payload),
                             headers={'Content-Type': 'application/json'}
                             )
    if response.status_code != 200:
        raise ValueError(
            'Request to slack returned an error %s, the response is:\n%s'
            % (response.status_code, response.text)
        )
    else:
        print("Payload sent")


class OW(object):
    KEYWORDS = keywords
    NKEYWORDS = n_keywords

    def __init__(self, s):
        self.s = s
        self.proxies = open_proxies()
        self.old_data = load_data('data.json')

    def get_product(self, url):
        r = make_request(url, self.proxies, self.s)
        if r is None:
            try:
                return self.old_data[url]
            except:
                return None

        if r == 404:
            if url in list(self.old_data.keys()):
                product = self.old_data[url]
                product['status'] = 'out of stock'
                send_embed(product)
                self.old_data.pop(product['id'], None)
            else:
                return None
        else:
            soup = BeautifulSoup(r.content, 'html.parser')
            name = ' '.join(soup.find('span', {'itemprop': 'name'}).text.strip().split())
            price = soup.find('span', {'class': 'price'}).text.strip()
            img = soup.find('img', {'itemprop': 'image'})['src']
            atc = []
            sizes = []
            status = 'in stock'
            if 'SOLD OUT' in r.text:
                status = 'out of stock'

            product = {
                'name': name,
                'price': price,
                'image': img,
                'status': status,
                'url': url,
                'sizes': sizes,
                'id': url,
                'atc': atc
            }

            if product['id'] not in self.old_data:
                send_embed(product)
            elif product['status'] != self.old_data[str(product['id'])]['status']:
                send_embed(product)
            elif any(x not in self.old_data[str(product['id'])]['sizes'] for x in product['sizes']):
                send_embed(product)

            self.old_data[product['id']] = product


    def find_matching(self):
        urls = []
        pages = []
        for query in queries:
            pages.append('https://wellgosh.com/catalogsearch/result/?q=' + query.replace(' ', '+'))
        for url in URLS:
            pages.append(url)
        for pag in pages:
            r = make_request(pag, self.proxies, self.s)
            soup = BeautifulSoup(r.content, 'html.parser')
            products = soup.find_all('a', {'class': 'productimagelink'})
            for prod in products:
                name = prod['title']
                if any(x.lower().strip() in name.lower() for x in self.KEYWORDS):
                    if any(x.lower().strip() in name.lower() for x in self.NKEYWORDS):
                        continue
                    urls.append(prod['href'])

        return urls



    def get_products(self, urls):
        # r = map(self.get_product, urls)
        r = []
        for url in urls:
            successful = False
            while not successful:
                try:
                    r.append(self.get_product(url))
                    successful = True
                except Exception as ex:
                    print(ex)
                time.sleep(delay_check_product)

        # r = [x for x in r if x]
        # out = {}
        # for item in r:
        #     out[item['id']] = item
        return self.old_data


def main(x):
    s = OW(x)
    urls = s.find_matching()
    urls += PRODUCTS
    out = s.get_products(urls)
    if out:
        save_new_data(out, 'data.json')


if __name__ == "__main__":
    proxies = open_proxies()
    s = cfscrape.CloudflareScraper()
    # make_request('https://www.solebox.com/en/Footwear/?&_artperpage=240', proxies, s)
    while True:
        try:
            start = time.time()
            main(s)
            print(time.time() - start)
            time.sleep(delay)
        except KeyboardInterrupt:
            print('Exiting...')
            sys.exit()
        except:
            print('Unexpected error: ', sys.exc_info()[0])
            continue