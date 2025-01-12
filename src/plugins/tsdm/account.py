from . import utils
from .config import tsdm_config
import requests
from nonebot.log import logger
from bs4 import BeautifulSoup
import os
import json
import base64
from requests_toolbelt import MultipartEncoder

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.132 ' \
             'Safari/537.36'
SESSION = requests.Session()


def on_start():
    utils.check_path(tsdm_config.tsdm_data_dir)
    if utils.check_file(tsdm_config.tsdm_data_dir, 'cookies.json'):
        logger.info('Cookies found, skip login.')
        SESSION.cookies = utils.load_cookies()
        return True
    else:
        logger.warning('Cookies not found, login required.')
        return False


# Get verify code image and return its filename
def get_verify_code_img() -> bytes:
    url = tsdm_config.tsdm_base_url + '/plugin.php'
    params = {
        'id': 'oracle:verify',
    }
    headers = {
        'User-Agent': USER_AGENT,
    }
    try:
        response = SESSION.get(url, params=params, headers=headers)
        # Response is an image, which should be saved to data dir
        filename = response.headers['X-Discuz-Session-Id'] + '.png'
        return response.content
    except Exception as e:
        logger.error('Get verify code failed: {}'.format(e))
        return b''


# Get actual verify code from user and login
# Return empty string if login succeed, otherwise return error message
def login(verify_code: str) -> str:
    url = tsdm_config.tsdm_base_url + '/member.php'
    params = {
        'mobile': 'yes',
        'tsdmapp': 3,
        'mod': 'logging',
        'action': 'login',
        'loginsubmit': 'yes',
    }
    data = {
        'username': tsdm_config.tsdm_username,
        'password': tsdm_config.tsdm_password,
        'tsdm_verify': verify_code,
        'fastloginfield': 'uid',
        'questionid': tsdm_config.tsdm_questionid,
        'answer': tsdm_config.tsdm_answer,
    }
    formdata = MultipartEncoder(fields=data)
    headers = {
        'User-Agent': USER_AGENT,
        'Content-Type': formdata.content_type,
    }
    try:
        response = SESSION.post(
            url, params=params, data=formdata, headers=headers)
        if response.json()["status"] == 0:
            logger.info('Login successful.')
            utils.save_cookies(SESSION.cookies)
            return ''
        else:
            logger.error('Login failed.')
            return response.text
    except Exception as e:
        logger.error('Login failed.')
        return 'Exception: {}'.format(e)


def refresh_cookie() -> str:
    url = tsdm_config.tsdm_base_url + '/home.php'
    params = {
        'mobile': 'yes',
        'tsdmapp': 3,
        'mod': 'space',
        'do': 'profile',
    }
    headers = {
        'User-Agent': USER_AGENT,
    }
    try:
        response = SESSION.get(url, params=params, headers=headers)
        if response.status_code == 200:
            logger.info('Refresh cookie successful.')
            utils.save_cookies(SESSION.cookies)
            return ''
        else:
            logger.error('Refresh cookie failed.')
            return response.text
    except Exception as e:
        logger.error('Refresh cookie failed.')
        return 'Exception: {}'.format(e)


def get_formhash() -> str:
    url = tsdm_config.tsdm_base_url + '/forum.php'
    params = {
        'mod': 'post',
        'action': 'newthread',
        'fid': '4',
        'tsdmapp': 1,
    }
    headers = {
        'User-Agent': USER_AGENT,
    }
    try:
        response = SESSION.get(url, params=params, headers=headers)
        if response.status_code == 200:
            res = response.json()
            return res['formhash']
        else:
            logger.error('Failed to fetch formhash.')
            return response.text
    except Exception as e:
        logger.error('Failed to fetch formhash.')
        return 'Exception: {}'.format(e)


def purchase(tid: str) -> str:
    url = tsdm_config.tsdm_base_url + '/forum.php'
    params = {
        'mod': 'misc',
        'action': 'pay',
        'mobile': 'yes',
        'paysubmit': 'yes',
        'infloat': 'yes',
        'inajax': 1
    }
    data = {
        'formhash': get_formhash(),
        'referer': tsdm_config.tsdm_base_url + '/forum.php?mod=viewthread&tid=' + tid,
        'tid': tid,
        'handlekey': 'pay',
    }
    formdata = MultipartEncoder(fields=data)
    headers = {
        'User-Agent': USER_AGENT,
        'Content-Type': formdata.content_type,
    }
    try:
        response = SESSION.post(
            url, params=params, data=formdata, headers=headers)
        if response.status_code == 200:
            res = response.text
            if res.find('主题购买成功') != -1 and res.find('抱歉，您已购买过此主题，请勿重复付费') != -1:
                logger.error('Purchase failed.')
                return res
            logger.info('Purchase successful.')
            return ''
        else:
            logger.error(response)
            logger.error('Purchase failed.')
            return response.text
    except Exception as e:
        logger.error('Purchase failed.')
        return 'Exception: {}'.format(e)


def get_forum_data(tid: str) -> str:
    url = tsdm_config.tsdm_base_url + '/forum.php'
    params = {
        'mod': 'viewthread',
        'tid': tid,
        'mobile': 'yes',
        'tsdmapp': 3,
    }
    headers = {
        'User-Agent': USER_AGENT,
    }
    try:
        response = SESSION.get(url, params=params, headers=headers)
        if response.status_code == 200:
            logger.info('Get forum data successful.')
            resp = response.text
            resp_json = json.loads(resp, strict=False)
            if resp_json['thread_paid'] == 0:
                res = purchase(tid)
                if res != '':
                    return resp_json['postlist'][0]['message']
                return get_forum_data(tid)
            return resp_json['postlist'][0]['message']
        else:
            logger.error('Get forum data failed.')
            return response.text
    except Exception as e:
        logger.error('Get forum data failed.')
        return 'Exception: {}'.format(e)
