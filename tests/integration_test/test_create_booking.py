# from src.constants.api_constants import BASE_URL, APIConstants, base_url
import pytest
import json

from src.helpers.api_requests_wrapper import post_requests
from src.constants.api_constants import APIConstants
from src.helpers.utils import common_headers_json
from src.helpers.payload_manager import payload_create_booking
from src.helpers.common_verification import verify_response_key_should_not_be_none, verify_http_status_code


class TestCreateBooking():
    def test_create_booking_tc1object(self):
        # URL, Headers, Payload
        response = post_requests(url=APIConstants.url_create_booking(),
                                 auth=None, headers=common_headers_json(),
                                 payload=payload_create_booking(),
                                 in_json=False)

        print(response)
        booking_id = response.json()["bookingid"]
        print(booking_id)
        verify_response_key_should_not_be_none(booking_id)
        verify_http_status_code(response,200)