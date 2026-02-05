#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# filename: config.py
# modified: 2019-09-10

import os
import re
from configparser import RawConfigParser, DuplicateSectionError
from collections import OrderedDict
from .environ import Environ
from .course import Course
from .rule import Mutex, Delay
from .utils import Singleton
from .const import DEFAULT_CONFIG_INI
from .exceptions import UserInputException

_reNamespacedSection = re.compile(r'^\s*(?P<ns>[^:]+?)\s*:\s*(?P<id>[^,]+?)\s*$')
_reCommaSep = re.compile(r'\s*,\s*')

environ = Environ()


class BaseConfig(object):

    def __init__(self, config_file=None):
        if self.__class__ is __class__:
            raise NotImplementedError
        file = os.path.normpath(os.path.abspath(config_file))
        if not os.path.exists(file):
            raise FileNotFoundError("Config file was not found: %s" % file)
        self._config = RawConfigParser()
        self._config.read(file, encoding="utf-8-sig")

    def get(self, section, key):
        return self._config.get(section, key)

    def getint(self, section, key):
        return self._config.getint(section, key)

    def getfloat(self, section, key):
        return self._config.getfloat(section, key)

    def getboolean(self, section, key):
        return self._config.getboolean(section, key)

    def get_optional(self, section, key, default=None):
        if self._config.has_option(section, key):
            return self._config.get(section, key)
        return default

    def get_optional_bool(self, section, key, default=False):
        if not self._config.has_option(section, key):
            return default
        try:
            return self._config.getboolean(section, key)
        except ValueError:
            raise UserInputException("Invalid boolean for %s.%s" % (section, key))

    def get_optional_list(self, section, key, default=None):
        if not self._config.has_option(section, key):
            return default if default is not None else []
        v = self._config.get(section, key)
        if v is None or v.strip() == "":
            return []
        return _reCommaSep.split(v)

    def getdict(self, section, options):
        assert isinstance(options, (list, tuple, set))
        d = dict(self._config.items(section))
        if not all(k in d for k in options):
            raise UserInputException("Incomplete course in section %r, %s must all exist." % (section, options))
        return d

    def getlist(self, section, option, *args, **kwargs):
        v = self.get(section, option, *args, **kwargs)
        return _reCommaSep.split(v)

    def ns_sections(self, ns):
        ns = ns.strip()
        ns_sects = OrderedDict()  # { id: str(section) }
        for s in self._config.sections():
            mat = _reNamespacedSection.match(s)
            if mat is None:
                continue
            if mat.group('ns') != ns:
                continue
            id_ = mat.group('id')
            if id_ in ns_sects:
                raise DuplicateSectionError("%s:%s" % (ns, id_))
            ns_sects[id_] = s
        return [(id_, s) for id_, s in ns_sects.items()]  # [ (id, str(section)) ]


class AutoElectiveConfig(BaseConfig, metaclass=Singleton):

    def __init__(self):
        super().__init__(environ.config_ini or DEFAULT_CONFIG_INI)

    ## Constraints

    ALLOWED_IDENTIFY = ("bzx", "bfx")

    ## Model

    # [user]

    @property
    def iaaa_id(self):
        return self.get("user", "student_id")

    @property
    def iaaa_password(self):
        return self.get("user", "password")

    @property
    def is_dual_degree(self):
        return self.getboolean("user", "dual_degree")

    @property
    def identity(self):
        return self.get("user", "identity").lower()

    # [client]

    @property
    def supply_cancel_page(self):
        return self.getint("client", "supply_cancel_page")

    @property
    def refresh_interval(self):
        return self.getfloat("client", "refresh_interval")

    @property
    def refresh_random_deviation(self):
        return self.getfloat("client", "random_deviation")

    @property
    def refresh_backoff_enable(self):
        return self.get_optional_bool("client", "refresh_backoff_enable", True)

    @property
    def refresh_backoff_factor(self):
        v = self.get_optional("client", "refresh_backoff_factor")
        if v is None or v == "":
            return 1.6
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid refresh_backoff_factor: %r" % v)
        return max(1.0, v)

    @property
    def refresh_backoff_max(self):
        v = self.get_optional("client", "refresh_backoff_max")
        if v is None or v == "":
            return 60.0
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid refresh_backoff_max: %r" % v)
        return max(0.0, v)

    @property
    def refresh_backoff_threshold(self):
        v = self.get_optional("client", "refresh_backoff_threshold")
        if v is None or v == "":
            return 2
        try:
            v = int(v)
        except ValueError:
            raise UserInputException("Invalid refresh_backoff_threshold: %r" % v)
        return max(1, v)

    @property
    def iaaa_client_timeout(self):
        return self.getfloat("client", "iaaa_client_timeout")

    @property
    def elective_client_timeout(self):
        return self.getfloat("client", "elective_client_timeout")

    @property
    def elective_client_pool_size(self):
        return self.getint("client", "elective_client_pool_size")

    @property
    def client_pool_reset_threshold(self):
        v = self.get_optional("client", "client_pool_reset_threshold")
        if v is None or v == "":
            return 5
        try:
            v = int(v)
        except ValueError:
            raise UserInputException("Invalid client_pool_reset_threshold: %r" % v)
        return max(1, v)

    @property
    def client_pool_reset_cooldown(self):
        v = self.get_optional("client", "client_pool_reset_cooldown")
        if v is None or v == "":
            return 300.0
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid client_pool_reset_cooldown: %r" % v)
        return max(0.0, v)

    @property
    def elective_client_max_life(self):
        return self.getint("client", "elective_client_max_life")

    @property
    def login_loop_interval(self):
        return self.getfloat("client", "login_loop_interval")

    @property
    def iaaa_backoff_enable(self):
        return self.get_optional_bool("client", "iaaa_backoff_enable", True)

    @property
    def iaaa_backoff_factor(self):
        v = self.get_optional("client", "iaaa_backoff_factor")
        if v is None or v == "":
            return 1.6
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid iaaa_backoff_factor: %r" % v)
        return max(1.0, v)

    @property
    def iaaa_backoff_max(self):
        v = self.get_optional("client", "iaaa_backoff_max")
        if v is None or v == "":
            return 60.0
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid iaaa_backoff_max: %r" % v)
        return max(0.0, v)

    @property
    def iaaa_backoff_threshold(self):
        v = self.get_optional("client", "iaaa_backoff_threshold")
        if v is None or v == "":
            return 2
        try:
            v = int(v)
        except ValueError:
            raise UserInputException("Invalid iaaa_backoff_threshold: %r" % v)
        return max(1, v)

    @property
    def is_print_mutex_rules(self):
        return self.getboolean("client", "print_mutex_rules")

    @property
    def is_debug_print_request(self):
        return self.getboolean("client", "debug_print_request")

    @property
    def is_debug_dump_request(self):
        return self.getboolean("client", "debug_dump_request")

    # [monitor]

    @property
    def monitor_host(self):
        return self.get("monitor", "host")

    @property
    def monitor_port(self):
        return self.getint("monitor", "port")

    @property
    def disable_push(self):
        return self.getboolean("notification", "disable_push")

    @property
    def wechat_token(self):
        return self.get("notification", "token")

    @property
    def verbosity(self):
        return self.getint("notification", "verbosity")

    @property
    def minimum_interval(self):
        return self.getfloat("notification", "minimum_interval")

    # [captcha]

    @property
    def captcha_provider(self):
        return (self.get_optional("captcha", "provider", "baidu") or "baidu").lower()

    @property
    def baidu_api_key(self):
        return self.get_optional("captcha", "baidu_api_key")

    @property
    def baidu_secret_key(self):
        return self.get_optional("captcha", "baidu_secret_key")

    @property
    def baidu_timeout(self):
        v = self.get_optional("captcha", "baidu_timeout")
        if v is None or v == "":
            return 10.0
        try:
            return float(v)
        except ValueError:
            raise UserInputException("Invalid baidu_timeout: %r" % v)

    @property
    def captcha_code_length(self):
        # Legacy: fixed captcha length.
        v = self.get_optional("captcha", "code_length")
        if v is None or v == "":
            return 4
        try:
            v = int(v)
        except ValueError:
            raise UserInputException("Invalid code_length: %r" % v)
        return max(1, v)

    @property
    def captcha_code_length_min(self):
        v_min = self.get_optional("captcha", "code_length_min")
        v_max = self.get_optional("captcha", "code_length_max")
        if v_min is None or v_min == "":
            # If user only sets max, default min to 1.
            if v_max is not None and v_max != "":
                return 1
            return self.captcha_code_length
        try:
            v_min = int(v_min)
        except ValueError:
            raise UserInputException("Invalid code_length_min: %r" % v_min)
        return max(1, v_min)

    @property
    def captcha_code_length_max(self):
        v_min = self.get_optional("captcha", "code_length_min")
        v_max = self.get_optional("captcha", "code_length_max")
        if v_max is None or v_max == "":
            # If user only sets min, default max to min.
            if v_min is not None and v_min != "":
                try:
                    v_min_i = int(v_min)
                except ValueError:
                    raise UserInputException("Invalid code_length_min: %r" % v_min)
                return max(1, v_min_i)
            return self.captcha_code_length
        try:
            v_max = int(v_max)
        except ValueError:
            raise UserInputException("Invalid code_length_max: %r" % v_max)
        return max(1, v_max)

    @property
    def gemini_api_key(self):
        return self.get_optional("captcha", "gemini_api_key")

    @property
    def gemini_model(self):
        return self.get_optional("captcha", "gemini_model")

    @property
    def gemini_timeout(self):
        v = self.get_optional("captcha", "gemini_timeout")
        if v is None or v == "":
            return 10.0
        try:
            return float(v)
        except ValueError:
            raise UserInputException("Invalid gemini_timeout: %r" % v)

    @property
    def gemini_max_output_tokens(self):
        v = self.get_optional("captcha", "gemini_max_output_tokens")
        if v is None or v == "":
            return 16
        try:
            v = int(v)
        except ValueError:
            raise UserInputException("Invalid gemini_max_output_tokens: %r" % v)
        return max(1, v)

    @property
    def dashscope_api_key(self):
        return self.get_optional("captcha", "dashscope_api_key")

    @property
    def dashscope_base_url(self):
        return self.get_optional("captcha", "dashscope_base_url")

    @property
    def dashscope_timeout(self):
        v = self.get_optional("captcha", "dashscope_timeout")
        if v is None or v == "":
            return 10.0
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid dashscope_timeout: %r" % v)

    @property
    def dashscope_max_output_tokens(self):
        v = self.get_optional("captcha", "dashscope_max_output_tokens")
        if v is None or v == "":
            return 16
        try:
            v = int(v)
        except ValueError:
            raise UserInputException("Invalid dashscope_max_output_tokens: %r" % v)
        return max(1, v)

    @property
    def dashscope_model(self):
        return self.get_optional("captcha", "dashscope_model")

    @property
    def dashscope_model_flash(self):
        return self.get_optional("captcha", "dashscope_model_flash")

    @property
    def dashscope_model_plus(self):
        return self.get_optional("captcha", "dashscope_model_plus")

    @property
    def dashscope_model_ocr(self):
        return self.get_optional("captcha", "dashscope_model_ocr")

    @property
    def captcha_degrade_failures(self):
        v = self.get_optional("captcha", "degrade_failures")
        if v is None or v == "":
            return 12
        try:
            v = int(v)
        except ValueError:
            raise UserInputException("Invalid degrade_failures: %r" % v)
        return max(1, v)

    @property
    def captcha_degrade_cooldown(self):
        v = self.get_optional("captcha", "degrade_cooldown")
        if v is None or v == "":
            return 60.0
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid degrade_cooldown: %r" % v)
        return max(1.0, v)

    @property
    def captcha_degrade_monitor_only(self):
        return self.get_optional_bool("captcha", "degrade_monitor_only", True)

    @property
    def captcha_degrade_notify(self):
        return self.get_optional_bool("captcha", "degrade_notify", True)

    @property
    def captcha_degrade_notify_interval(self):
        v = self.get_optional("captcha", "degrade_notify_interval")
        if v is None or v == "":
            return 60.0
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid degrade_notify_interval: %r" % v)
        return max(1.0, v)

    @property
    def captcha_switch_on_degrade(self):
        return self.get_optional_bool("captcha", "switch_on_degrade", True)

    @property
    def captcha_fallback_providers(self):
        return [s.strip().lower() for s in self.get_optional_list("captcha", "fallback_providers")]

    # [resilience]

    @property
    def critical_cooldown_seconds(self):
        v = self.get_optional("resilience", "critical_cooldown_seconds")
        if v is None or v == "":
            return 600.0
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid critical_cooldown_seconds: %r" % v)
        return max(0.0, v)

    @property
    def critical_notify_interval(self):
        v = self.get_optional("resilience", "critical_notify_interval")
        if v is None or v == "":
            return 300.0
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid critical_notify_interval: %r" % v)
        return max(0.0, v)

    @property
    def critical_reset_cache(self):
        return self.get_optional_bool("resilience", "critical_reset_cache", True)

    @property
    def critical_reset_sessions(self):
        return self.get_optional_bool("resilience", "critical_reset_sessions", True)

    @property
    def failure_notify_threshold(self):
        v = self.get_optional("resilience", "failure_notify_threshold")
        if v is None or v == "":
            return 10
        try:
            v = int(v)
        except ValueError:
            raise UserInputException("Invalid failure_notify_threshold: %r" % v)
        return max(1, v)

    @property
    def failure_notify_interval(self):
        v = self.get_optional("resilience", "failure_notify_interval")
        if v is None or v == "":
            return 300.0
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid failure_notify_interval: %r" % v)
        return max(0.0, v)

    @property
    def failure_cooldown_seconds(self):
        v = self.get_optional("resilience", "failure_cooldown_seconds")
        if v is None or v == "":
            return 180.0
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid failure_cooldown_seconds: %r" % v)
        return max(0.0, v)

    @property
    def not_in_operation_cooldown_seconds(self):
        v = self.get_optional("resilience", "not_in_operation_cooldown_seconds")
        if v is None or v == "":
            return 30.0
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid not_in_operation_cooldown_seconds: %r" % v)
        return max(0.0, v)

    @property
    def not_in_operation_min_refresh(self):
        v = self.get_optional("resilience", "not_in_operation_min_refresh")
        if v is None or v == "":
            return 5.0
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid not_in_operation_min_refresh: %r" % v)
        return max(0.0, v)

    @property
    def not_in_operation_skip_pool_reset(self):
        return self.get_optional_bool("resilience", "not_in_operation_skip_pool_reset", True)

    @property
    def html_parse_error_threshold(self):
        v = self.get_optional("resilience", "html_parse_error_threshold")
        if v is None or v == "":
            return 3
        try:
            v = int(v)
        except ValueError:
            raise UserInputException("Invalid html_parse_error_threshold: %r" % v)
        return max(0, v)

    @property
    def html_parse_cooldown_seconds(self):
        v = self.get_optional("resilience", "html_parse_cooldown_seconds")
        if v is None or v == "":
            return 10.0
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid html_parse_cooldown_seconds: %r" % v)
        return max(0.0, v)

    @property
    def html_parse_reset_sessions(self):
        return self.get_optional_bool("resilience", "html_parse_reset_sessions", True)

    @property
    def auth_error_threshold(self):
        v = self.get_optional("resilience", "auth_error_threshold")
        if v is None or v == "":
            return 5
        try:
            v = int(v)
        except ValueError:
            raise UserInputException("Invalid auth_error_threshold: %r" % v)
        return max(0, v)

    @property
    def auth_cooldown_seconds(self):
        v = self.get_optional("resilience", "auth_cooldown_seconds")
        if v is None or v == "":
            return 10.0
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid auth_cooldown_seconds: %r" % v)
        return max(0.0, v)

    @property
    def auth_reset_sessions(self):
        return self.get_optional_bool("resilience", "auth_reset_sessions", True)

    @property
    def captcha_adaptive_enable(self):
        return self.get_optional_bool("captcha", "adaptive_enable", False)

    @property
    def captcha_adaptive_min_samples(self):
        v = self.get_optional("captcha", "adaptive_min_samples")
        if v is None or v == "":
            return 10
        try:
            v = int(v)
        except ValueError:
            raise UserInputException("Invalid adaptive_min_samples: %r" % v)
        return max(1, v)

    @property
    def captcha_adaptive_epsilon(self):
        v = self.get_optional("captcha", "adaptive_epsilon")
        if v is None or v == "":
            return 0.1
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid adaptive_epsilon: %r" % v)
        return max(0.0, v)

    @property
    def captcha_adaptive_latency_alpha(self):
        v = self.get_optional("captcha", "adaptive_latency_alpha")
        if v is None or v == "":
            return 0.2
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid adaptive_latency_alpha: %r" % v)
        return min(1.0, max(0.01, v))

    @property
    def captcha_adaptive_h_alpha(self):
        v = self.get_optional("captcha", "adaptive_h_alpha")
        if v is None or v == "":
            return 0.2
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid adaptive_h_alpha: %r" % v)
        return min(1.0, max(0.01, v))

    @property
    def captcha_adaptive_h_init(self):
        v = self.get_optional("captcha", "adaptive_h_init")
        if v is None or v == "":
            return None
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid adaptive_h_init: %r" % v)
        return max(0.0, v)

    @property
    def captcha_adaptive_update_interval(self):
        v = self.get_optional("captcha", "adaptive_update_interval")
        if v is None or v == "":
            return 20
        try:
            v = int(v)
        except ValueError:
            raise UserInputException("Invalid adaptive_update_interval: %r" % v)
        return max(0, v)

    @property
    def captcha_adaptive_fail_streak_degrade(self):
        v = self.get_optional("captcha", "adaptive_fail_streak_degrade")
        if v is None or v == "":
            return 3
        try:
            v = int(v)
        except ValueError:
            raise UserInputException("Invalid adaptive_fail_streak_degrade: %r" % v)
        return max(0, v)

    @property
    def captcha_adaptive_score_alpha(self):
        v = self.get_optional("captcha", "adaptive_score_alpha")
        if v is None or v == "":
            return 0.4
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid adaptive_score_alpha: %r" % v)
        return max(0.0, v)

    @property
    def captcha_adaptive_score_beta(self):
        v = self.get_optional("captcha", "adaptive_score_beta")
        if v is None or v == "":
            return 0.6
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid adaptive_score_beta: %r" % v)
        return max(0.0, v)

    @property
    def captcha_sample_enable(self):
        return self.get_optional_bool("captcha", "sample_enable", False)

    @property
    def captcha_sample_rate(self):
        v = self.get_optional("captcha", "sample_rate")
        if v is None or v == "":
            return 0.05
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid sample_rate: %r" % v)
        return min(1.0, max(0.0, v))

    @property
    def captcha_sample_dir(self):
        v = self.get_optional("captcha", "sample_dir")
        if v is None or v == "":
            return "cache/captcha_samples"
        return v

    @property
    def captcha_probe_enabled(self):
        return self.get_optional_bool("captcha", "probe_enabled", False)

    @property
    def captcha_probe_interval(self):
        v = self.get_optional("captcha", "probe_interval")
        if v is None or v == "":
            return 30.0
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid probe_interval: %r" % v)
        return max(1.0, v)

    @property
    def captcha_probe_backoff(self):
        v = self.get_optional("captcha", "probe_backoff")
        if v is None or v == "":
            return 600.0
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid probe_backoff: %r" % v)
        return max(1.0, v)

    @property
    def captcha_probe_random_deviation(self):
        v = self.get_optional("captcha", "probe_random_deviation")
        if v is None or v == "":
            return 0.1
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid probe_random_deviation: %r" % v)
        return min(1.0, max(0.0, v))

    @property
    def captcha_adaptive_report_interval(self):
        v = self.get_optional("captcha", "adaptive_report_interval")
        if v is None or v == "":
            return 0
        try:
            v = int(v)
        except ValueError:
            raise UserInputException("Invalid adaptive_report_interval: %r" % v)
        return max(0, v)

    @property
    def runtime_stat_report_interval(self):
        v = self.get_optional("runtime", "report_interval")
        if v is None or v == "":
            return 0
        try:
            v = int(v)
        except ValueError:
            raise UserInputException("Invalid runtime report_interval: %r" % v)
        return max(0, v)

    @property
    def runtime_rate_window_seconds(self):
        v = self.get_optional("runtime", "rate_window_seconds")
        if v is None or v == "":
            return 60.0
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid runtime rate_window_seconds: %r" % v)
        return max(1.0, v)

    @property
    def runtime_error_aggregate_interval(self):
        v = self.get_optional("runtime", "error_aggregate_interval")
        if v is None or v == "":
            return 60.0
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid runtime error_aggregate_interval: %r" % v)
        return max(0.0, v)

    # [rate_limit]

    @property
    def rate_limit_enable(self):
        return self.get_optional_bool("rate_limit", "enable", default=False)

    @property
    def rate_limit_global_rps(self):
        v = self.get_optional("rate_limit", "global_rps")
        if v is None or v == "":
            return 0.0
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid rate_limit global_rps: %r" % v)
        return max(0.0, v)

    @property
    def rate_limit_global_burst(self):
        v = self.get_optional("rate_limit", "global_burst")
        if v is None or v == "":
            return 0.0
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid rate_limit global_burst: %r" % v)
        return max(0.0, v)

    @property
    def rate_limit_elective_rps(self):
        v = self.get_optional("rate_limit", "elective_rps")
        if v is None or v == "":
            return 0.0
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid rate_limit elective_rps: %r" % v)
        return max(0.0, v)

    @property
    def rate_limit_elective_burst(self):
        v = self.get_optional("rate_limit", "elective_burst")
        if v is None or v == "":
            return 0.0
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid rate_limit elective_burst: %r" % v)
        return max(0.0, v)

    @property
    def rate_limit_iaaa_rps(self):
        v = self.get_optional("rate_limit", "iaaa_rps")
        if v is None or v == "":
            return 0.0
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid rate_limit iaaa_rps: %r" % v)
        return max(0.0, v)

    @property
    def rate_limit_iaaa_burst(self):
        v = self.get_optional("rate_limit", "iaaa_burst")
        if v is None or v == "":
            return 0.0
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid rate_limit iaaa_burst: %r" % v)
        return max(0.0, v)

    # [captcha]

    @property
    def captcha_probe_pool_size(self):
        v = self.get_optional("captcha", "probe_pool_size")
        if v is None or v == "":
            return 1
        try:
            v = int(v)
        except ValueError:
            raise UserInputException("Invalid probe_pool_size: %r" % v)
        return max(0, v)

    @property
    def captcha_probe_share_pool(self):
        return self.get_optional_bool("captcha", "probe_share_pool", False)

    # [offline]

    @property
    def offline_enabled(self):
        return self.get_optional_bool("offline", "enable", True)

    @property
    def offline_error_threshold(self):
        v = self.get_optional("offline", "error_threshold", 3)
        try:
            v = int(v)
        except ValueError:
            raise UserInputException("Invalid offline.error_threshold: %r" % v)
        if v < 1:
            raise UserInputException("Invalid offline.error_threshold: %r" % v)
        return v

    @property
    def offline_cooldown_seconds(self):
        v = self.get_optional("offline", "cooldown_seconds", 10)
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid offline.cooldown_seconds: %r" % v)
        if v < 0:
            raise UserInputException("Invalid offline.cooldown_seconds: %r" % v)
        return v

    @property
    def offline_probe_interval(self):
        v = self.get_optional("offline", "probe_interval", 15)
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid offline.probe_interval: %r" % v)
        if v < 1:
            raise UserInputException("Invalid offline.probe_interval: %r" % v)
        return v

    @property
    def offline_probe_timeout(self):
        v = self.get_optional("offline", "probe_timeout", 5)
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid offline.probe_timeout: %r" % v)
        if v <= 0:
            raise UserInputException("Invalid offline.probe_timeout: %r" % v)
        return v

    @property
    def offline_observe_seconds(self):
        v = self.get_optional("offline", "observe_seconds", 30)
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid offline.observe_seconds: %r" % v)
        if v < 0:
            raise UserInputException("Invalid offline.observe_seconds: %r" % v)
        return v

    @property
    def offline_observe_min_refresh(self):
        v = self.get_optional("offline", "observe_min_refresh", 2)
        try:
            v = float(v)
        except ValueError:
            raise UserInputException("Invalid offline.observe_min_refresh: %r" % v)
        if v < 0:
            raise UserInputException("Invalid offline.observe_min_refresh: %r" % v)
        return v

    # [course]

    @property
    def courses(self):
        cs = OrderedDict()  # { id: Course }
        rcs = {}
        for id_, s in self.ns_sections('course'):
            d = self.getdict(s, ('name', 'class', 'school'))
            d.update(class_no=d.pop('class'))
            c = Course(**d)
            cs[id_] = c
            rid = rcs.get(c)
            if rid is not None:
                raise UserInputException("Duplicated courses in sections 'course:%s' and 'course:%s'" % (rid, id_))
            rcs[c] = id_
        return cs

    # [mutex]

    @property
    def mutexes(self):
        ms = OrderedDict()  # { id: Mutex }
        for id_, s in self.ns_sections('mutex'):
            lst = self.getlist(s, 'courses')
            ms[id_] = Mutex(lst)
        return ms

    # [delay]

    @property
    def delays(self):
        ds = OrderedDict()  # { id: Delay }
        cid_id = {}  # { cid: id }
        for id_, s in self.ns_sections('delay'):
            cid = self.get(s, 'course')
            threshold = self.getint(s, 'threshold')
            if not threshold > 0:
                raise UserInputException("Invalid threshold %d in 'delay:%s', threshold > 0 must be satisfied" % (threshold, id_))
            id0 = cid_id.get(cid)
            if id0 is not None:
                raise UserInputException("Duplicated delays of 'course:%s' in 'delay:%s' and 'delay:%s'" % (cid, id0, id_))
            cid_id[cid] = id_
            ds[id_] = Delay(cid, threshold)
        return ds

    ## Method

    def check_identify(self, identity):
        limited = self.__class__.ALLOWED_IDENTIFY
        if identity not in limited:
            raise ValueError("unsupported identity %s for elective, identity must be in %s" % (identity, limited))

    def check_supply_cancel_page(self, page):
        if page <= 0:
            raise ValueError("supply_cancel_page must be positive number, not %s" % page)

    def get_user_subpath(self):
        if self.is_dual_degree:
            identity = self.identity
            self.check_identify(identity)
            if identity == "bfx":
                return "%s_%s" % (self.iaaa_id, identity)
        return self.iaaa_id
