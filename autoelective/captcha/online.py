import base64
from io import BytesIO
import json
import requests
from PIL import Image
import urllib
from .captcha import Captcha
from ..config import BaseConfig
from .._internal import get_abs_path
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

API_KEY = "PRhT07TN75zOBWK06VlWx0Yh"
SECRET_KEY = "frHeo730hR0BsfvLCpeVqmRKXFrQcA2o"

def get_access_token():
        """
        使用 AK，SK 生成鉴权签名（Access Token）
        :return: access_token，或是None(如果错误)
        """
        url = "https://aip.baidubce.com/oauth/2.0/token"
        params = {"grant_type": "client_credentials", "client_id": API_KEY, "client_secret": SECRET_KEY}
        return str(requests.post(url, params=params).json().get("access_token"))


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

class TTShituRecognizer(object):

    # _RECOGNIZER_URL = "http://api.ttshitu.com/base64"
    

    def __init__(self):
        # self._config = APIConfig()
        self.url= "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic?access_token=" + get_access_token()
        
    def recognize(self, raw):
        
        # image=get_file_content_as_base64(BytesIO(raw),1)
        image=TTShituRecognizer._to_b64(raw)
        image=urllib.parse.quote_plus(image)
        payload='image='+image+"&detect_direction=true&paragraph=false&probability=false&multidirectional_recognize=true"
        headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json'
        }
        response = requests.request("POST", self.url, headers=headers, data=payload.encode("utf-8"))
        # _typeid_ = self._config.typeid
        # encode = TTShituRecognizer._to_b64(raw)
        # data = {
        #     "username": self._config.uname, 
        #     "password": self._config.pwd,
        #     "image": encode,
        #     "typeid": _typeid_
        # }
        try:
            result=json.loads(response.text)
            # result = json.loads(requests.post(TTShituRecognizer._RECOGNIZER_URL, json=data, timeout=20).text)
        except requests.Timeout:
            raise OperationTimeoutError(msg="Recognizer connection time out")
        except requests.ConnectionError:
            raise OperationFailedError(msg="Unable to coonnect to the recognizer")
        
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
