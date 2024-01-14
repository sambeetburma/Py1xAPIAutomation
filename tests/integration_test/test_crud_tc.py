from src.constants.api_constants import BASE_URL, APIConstants, base_url


def test_crud():
    print("\n", BASE_URL)

    url_direct_func = base_url()
    print(url_direct_func)

    url_class = APIConstants.base_url()
    print(url_class)
