"""Telling a rate limit apart from a permission failure."""
import time

from gh_triage import throttle_delay

PERM = '{"message":"Resource not accessible by integration"}'
SECONDARY = '{"message":"You have exceeded a secondary rate limit."}'
PRIMARY = '{"message":"API rate limit exceeded for user."}'


def test_retry_after_is_honoured():
    assert throttle_delay({"retry-after": "17"}, 403, SECONDARY, 0) == 17


def test_exhausted_quota_waits_for_the_reset():
    headers = {"x-ratelimit-remaining": "0",
               "x-ratelimit-reset": str(int(time.time()) + 600)}
    assert abs(throttle_delay(headers, 403, PRIMARY, 0) - 600) <= 2


def test_exhausted_quota_without_a_reset_falls_back():
    assert throttle_delay({"x-ratelimit-remaining": "0"}, 403, PRIMARY, 0) == 60


def test_secondary_limit_backs_off_and_grows():
    assert throttle_delay({}, 403, SECONDARY, 0) == 30
    assert throttle_delay({}, 403, SECONDARY, 2) == 120


def test_a_bare_403_is_a_permission_error_not_a_wait():
    """Retrying this would sleep for minutes on something that never clears."""
    assert throttle_delay({}, 403, PERM, 0) is None


def test_quota_remaining_means_a_403_is_real():
    assert throttle_delay({"x-ratelimit-remaining": "4213"}, 403, PERM, 0) is None


def test_a_bare_429_is_still_throttling():
    assert throttle_delay({}, 429, "", 0) == 30


def test_other_codes_are_never_throttling():
    assert throttle_delay({}, 404, '{"message":"Not Found"}', 0) is None
    assert throttle_delay({}, 422, '{"message":"Validation failed"}', 0) is None
    assert throttle_delay({}, 500, "", 0) is None


def test_header_lookup_is_case_insensitive():
    """Real responses arrive as HTTPMessage with Retry-After capitalised."""
    import http.client
    m = http.client.HTTPMessage()
    m["Retry-After"] = "9"
    assert throttle_delay(m, 403, SECONDARY, 0) == 9
