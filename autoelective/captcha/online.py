import base64
from io import BytesIO
import json
import os
import time
import requests
from PIL import Image
import urllib
from .captcha import Captcha
from .registry import CaptchaRecognizer, register_recognizer
from .._internal import get_abs_path
from ..config import AutoElectiveConfig
from ..exceptions import OperationFailedError, OperationTimeoutError, RecognizerError

class APIConfig(object):

    _DEFAULT_CONFIG_PATH = '../apikey.json'

    def __init__(self, path=_DEFAULT_CONFIG_PATH):
        with open(get_abs_path(path), 'r') as handle:
            self._apikey = json.load(handle)
        try:
            assert 'username' in self._apikey.keys() and 'password' in self._apikey.keys()
            assert 'RecognitionTypeid' in self._apikey.keys()
        except AssertionError as e:
            print("Check your apikey.json for necessary key")
            exit(-1)

    @property
    def uname(self):
        return self._apikey['username']

    @property
    def pwd(self):
        return self._apikey['password']

    @property
    def typeid(self):
        return int(self._apikey['RecognitionTypeid'])

def get_access_token(api_key, secret_key, timeout, session=None):
    """
    使用 AK，SK 生成鉴权签名（Access Token）
    :return: access_token，或是None(如果错误)
    """
    if not api_key or not secret_key:
        raise RecognizerError(
            msg="Baidu OCR keys not configured. Set [captcha] baidu_api_key/baidu_secret_key "
                "or environment variables BAIDU_OCR_API_KEY/BAIDU_OCR_SECRET_KEY."
        )
    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {"grant_type": "client_credentials", "client_id": api_key, "client_secret": secret_key}
    sess = session or requests
    try:
        resp = sess.post(url, params=params, timeout=timeout)
    except requests.Timeout:
        raise OperationTimeoutError(msg="Recognizer connection time out")
    except requests.ConnectionError:
        raise OperationFailedError(msg="Unable to connect to the recognizer")
    except requests.RequestException as e:
        raise OperationFailedError(msg="Recognizer request failed: %s" % e)
    try:
        data = resp.json()
    except ValueError:
        raise RecognizerError(msg="Recognizer ERROR: Invalid JSON response")
    token = data.get("access_token")
    if not token:
        msg = data.get("error_msg") or "Unable to obtain access token"
        raise RecognizerError(msg="Recognizer ERROR: %s" % msg)
    expires_in = data.get("expires_in")
    return token, expires_in


def get_file_content_as_base64(path, urlencoded=False):
    """
    获取文件base64编码
    :param path: 文件路径
    :param urlencoded: 是否对结果进行urlencoded 
    :return: base64编码信息
    """
    with open(path, "rb") as f:
        content = base64.b64encode(f.read()).decode("utf8")
        if urlencoded:
            content = urllib.parse.quote_plus(content)
    return content 

@register_recognizer
class BaiduOCRRecognizer(CaptchaRecognizer):
    name = "baidu"

    # _RECOGNIZER_URL = "http://api.ttshitu.com/base64"
    

    def __init__(self):
        # self._config = APIConfig()
        config = AutoElectiveConfig()
        self._api_key = config.baidu_api_key or os.getenv("BAIDU_OCR_API_KEY")
        self._secret_key = config.baidu_secret_key or os.getenv("BAIDU_OCR_SECRET_KEY")
        self._timeout = config.baidu_timeout
        self._session = requests.Session()
        self._access_token = None
        self._access_token_expire_at = 0
        self._refresh_token()
        self.url = (
            "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic?access_token="
            + self._access_token
        )

    def _refresh_token(self):
        token, expires_in = get_access_token(
            self._api_key,
            self._secret_key,
            self._timeout,
            session=self._session,
        )
        self._access_token = token
        try:
            expires_in = int(expires_in)
        except Exception:
            expires_in = 0
        if expires_in > 60:
            self._access_token_expire_at = time.time() + expires_in - 60
        else:
            self._access_token_expire_at = time.time() + 3600

    def _ensure_token(self):
        if not self._access_token or time.time() >= self._access_token_expire_at:
            self._refresh_token()
            self.url = (
                "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic?access_token="
                + self._access_token
            )
        
    def recognize(self, raw):
        self._ensure_token()
        
        # image=get_file_content_as_base64(BytesIO(raw),1)
        image=self._to_b64(raw)
        image=urllib.parse.quote_plus(image)
        payload='image='+image+"&detect_direction=true&paragraph=false&probability=false&multidirectional_recognize=true"
        headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json'
        }
        try:
            response = requests.request(
                "POST",
                self.url,
                headers=headers,
                data=payload.encode("utf-8"),
                timeout=self._timeout,
            )
        except requests.Timeout:
            raise OperationTimeoutError(msg="Recognizer connection time out")
        except requests.ConnectionError:
            raise OperationFailedError(msg="Unable to connect to the recognizer")
        except requests.RequestException as e:
            raise OperationFailedError(msg="Recognizer request failed: %s" % e)
        # _typeid_ = self._config.typeid
        # encode = TTShituRecognizer._to_b64(raw)
        # data = {
        #     "username": self._config.uname, 
        #     "password": self._config.pwd,
        #     "image": encode,
        #     "typeid": _typeid_
        # }
        try:
            result = response.json()
            # result = json.loads(requests.post(TTShituRecognizer._RECOGNIZER_URL, json=data, timeout=20).text)
        except ValueError:
            raise RecognizerError(msg="Recognizer ERROR: Invalid JSON response")
        
        if 'error_code' not in result.keys():
            # 防止index error
            if len(result['words_result'])==0:
                raise RecognizerError(msg="Recognizer ERROR: Empty result")
            return Captcha(result['words_result'][0]['words'], None, None, None, None)
        else:
            raise RecognizerError(msg="Recognizer ERROR: %s" % result["error_msg"])
        # if result["success"]:
        #     return Captcha(result["data"]["result"], None, None, None, None)
        # else: # fail
        #     raise RecognizerError(msg="Recognizer ERROR: %s" % result["message"])
    
    @staticmethod
    @staticmethod
    def _to_b64(raw):
        im = Image.open(BytesIO(raw))
        try:
            if im.is_animated:
                oim = im
                oim.seek(oim.n_frames-1)
                im = Image.new('RGB', oim.size)
                im.paste(oim)
        except AttributeError:
            pass
        buffer = BytesIO()
        im.convert('RGB').save(buffer, format='JPEG')
        b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return b64


# Backward-compatible alias
TTShituRecognizer = BaiduOCRRecognizer
