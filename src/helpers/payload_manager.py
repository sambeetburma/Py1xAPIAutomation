def payload_create_booking():
    payload = {
    "bookingid": 3945,
    "booking": {
        "firstname": "Jim",
        "lastname": "Brown",
        "totalprice": 444,
        "depositpaid": True,
        "bookingdates": {
            "checkin": "2018-01-01",
            "checkout": "2019-01-01"
        },
        "additionalneeds": "Breakfast"
        }
    }
    return payload
