import re

from notifications.models import Notification

_TAB = re.compile(r"[?&]tab=([a-z_]+)$")
_ORDER = re.compile(r"^/elon/(\d+)/$")


def notify(user, text: str, url: str = "") -> None:
    """Add a notification for ``user`` (an account, or an ArchitectProfile — its account is used).
    Does nothing for someone who doesn't exist, so callers never have to check.

    ``url`` is the page the news belongs to: an architect's tab (``...?tab=orders``) or a
    client's order (``/elon/12/``). The red number on that tab / order shows it until the
    person opens that place."""
    user = getattr(user, "user", user)
    if user is None:
        return
    Notification.objects.create(user=user, text=text[:300], url=url)


def unread_count(user) -> int:
    return Notification.objects.filter(user=user, is_read=False).count()


def _unread(user):
    return Notification.objects.filter(user=user, is_read=False)


def tab_badges(user) -> dict:
    """{tab key: how many unread notifications point at that tab}."""
    counts = {}
    for url in _unread(user).values_list("url", flat=True):
        match = _TAB.search(url or "")
        if match:
            counts[match.group(1)] = counts.get(match.group(1), 0) + 1
    return counts


def take_tab_notifications(user, tab: str) -> list:
    """The unread news for one tab (their texts), marked as read: the person is looking at it now."""
    pending = list(_unread(user).filter(url__endswith=f"tab={tab}"))
    if pending:
        Notification.objects.filter(pk__in=[n.pk for n in pending]).update(is_read=True)
    return [n.text for n in pending]


def order_badges(user) -> dict:
    """{order id: unread count} for a client's orders."""
    counts = {}
    for url in _unread(user).values_list("url", flat=True):
        match = _ORDER.match(url or "")
        if match:
            counts[int(match.group(1))] = counts.get(int(match.group(1)), 0) + 1
    return counts


def order_news(user) -> dict:
    """{order id: [unread texts]} so the client's home page can say what happened ("... ariza yubordi")."""
    news = {}
    for url, text in _unread(user).order_by("-created_at").values_list("url", "text"):
        match = _ORDER.match(url or "")
        if match:
            news.setdefault(int(match.group(1)), []).append(text)
    return news


def take_url_notifications(user, url: str) -> list:
    pending = list(_unread(user).filter(url=url))
    if pending:
        Notification.objects.filter(pk__in=[n.pk for n in pending]).update(is_read=True)
    return [n.text for n in pending]


def workspace_notices(user, current_tab: str) -> dict:
    """What an architect's panel needs: the news for the tab being opened (shown once, then
    cleared) and the red numbers for the other tabs."""
    news = take_tab_notifications(user, current_tab)
    return {"new_here": news, "tab_badges": tab_badges(user)}
