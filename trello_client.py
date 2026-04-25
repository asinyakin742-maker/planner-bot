import requests


def create_trello_card(
    api_key: str,
    token: str,
    list_id: str,
    title: str,
    description: str,
    due_date: str = None,
    trello_member_id: str = None,
):
    url = "https://api.trello.com/1/cards"
    query = {
        "key": api_key,
        "token": token,
        "idList": list_id,
        "name": title,
        "desc": description,
    }

    if due_date:
        query["due"] = due_date
    if trello_member_id:
        query["idMembers"] = [trello_member_id]

    response = requests.post(url, params=query, timeout=20)
    return response.status_code, response.text
