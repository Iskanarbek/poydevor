from django.db.models import Q

from architects.models import SINGLE_SERVICES, ObjectType, PortfolioProject, ServiceType, Style

# (key in the address, label, lowest, highest) in US dollars; the last one has no upper limit ("$5000+").
SERVICES = [str(v) for v in SINGLE_SERVICES]      # a project doing "both" shows under either of these
PRICE_RANGES = [
    ("0-500", "$500 gacha", 0, 500),
    ("500-1000", "$500 – $1000", 500, 1000),
    ("1000-2000", "$1000 – $2000", 1000, 2000),
    ("2000-5000", "$2000 – $5000", 2000, 5000),
    ("5000-up", "$5000 va undan ko'p", 5000, None),
]


def _url(request, param, value):
    """The current address with one filter changed (or removed when value is None)."""
    query = request.GET.copy()
    query.pop("page", None)
    if value is None:
        query.pop(param, None)
    else:
        query[param] = value
    encoded = query.urlencode()
    return f"{request.path}?{encoded}" if encoded else request.path


def _group(request, title, param, options):
    chosen = request.GET.get(param)
    return {
        "title": title,
        "options": [{"label": "Barchasi", "url": _url(request, param, None), "active": not chosen}] + [
            {"label": label, "url": _url(request, param, value), "active": chosen == str(value)}
            for value, label in options
        ],
    }


def gallery_context(request):
    """The projects of every architect for the gallery, narrowed by the chosen filters (kind of
    job, kind of object, price range, style). Used by the clients' home page and the public
    gallery page."""
    get = request.GET
    projects = (
        PortfolioProject.objects.visible()
        .select_related("architect__user", "architect__studio_owned", "style")
        .prefetch_related("images")
    )
    filtered = False
    style_id = get.get("style")
    if style_id and style_id.isdigit():
        projects, filtered = projects.filter(style_id=style_id), True
    if get.get("service") == ServiceType.BOTH:
        projects, filtered = projects.filter(service_type=ServiceType.BOTH), True
    elif get.get("service") in SERVICES:
        projects, filtered = projects.filter(Q(service_type=get["service"]) | Q(service_type=ServiceType.BOTH)), True
    if get.get("object") in ObjectType.values:
        projects, filtered = projects.filter(object_type=get["object"]), True
    price = next((r for r in PRICE_RANGES if r[0] == get.get("price")), None)
    if price:
        _, _, low, high = price
        # A project without a price is never "inside" a range.
        projects = projects.filter(Q(price_usd__gte=low) & (Q(price_usd__lt=high) if high else Q()))
        filtered = True

    groups = [
        _group(request, "Xizmat turi", "service", [(v, ServiceType(v).label) for v in SERVICES + [ServiceType.BOTH.value]]),
        _group(request, "Obyekt turi", "object", [(v, ObjectType(v).label) for v in ObjectType.values]),
        _group(request, "Narx", "price", [(key, label) for key, label, _, _ in PRICE_RANGES]),
        _group(request, "Uslub", "style", [(s.pk, s.name) for s in Style.objects.all()]),
    ]
    return {
        "projects": projects,
        "filter_groups": groups,
        "filtered": filtered,
        "filter_count": _active_count(request),
        "clear_url": _clear_url(request),
        # kept for the older templates/tests that only knew about the style chips
        "styles": Style.objects.all(),
        "selected_style": style_id,
    }


FILTER_PARAMS = ("service", "object", "price", "style")


def _active_count(request) -> int:
    return sum(1 for key in FILTER_PARAMS if request.GET.get(key))


def _clear_url(request) -> str:
    """The current address without any filter (other parameters, such as the tab, stay)."""
    query = request.GET.copy()
    for key in FILTER_PARAMS:
        query.pop(key, None)
    encoded = query.urlencode()
    return f"{request.path}?{encoded}" if encoded else request.path


def filter_open_orders(request, applications):
    """The same filters for the architects' market ("E'lonlar bozori"): kind of job, kind of
    object, price (an order matches a range when its estimated price overlaps it) and style."""
    get = request.GET
    filtered = False
    if get.get("service") == ServiceType.BOTH:
        applications, filtered = applications.filter(service_type=ServiceType.BOTH), True
    elif get.get("service") in SERVICES:
        applications, filtered = applications.filter(Q(service_type=get["service"]) | Q(service_type=ServiceType.BOTH)), True
    if get.get("object") in ObjectType.values:
        applications, filtered = applications.filter(object_type=get["object"]), True
    style_id = get.get("style")
    if style_id and style_id.isdigit():
        applications, filtered = applications.filter(interior_style_id=style_id), True
    price = next((r for r in PRICE_RANGES if r[0] == get.get("price")), None)
    if price:
        _, _, low, high = price
        applications = applications.filter(estimate_max__gte=low)
        if high:
            applications = applications.filter(estimate_min__lt=high)
        filtered = True
    groups = [
        _group(request, "Xizmat turi", "service", [(v, ServiceType(v).label) for v in SERVICES + [ServiceType.BOTH.value]]),
        _group(request, "Obyekt turi", "object", [(v, ObjectType(v).label) for v in ObjectType.values]),
        _group(request, "Narx", "price", [(key, label) for key, label, _, _ in PRICE_RANGES]),
        _group(request, "Uslub", "style", [(s.pk, s.name) for s in Style.objects.all()]),
    ]
    return applications, {
        "filter_groups": groups, "filtered": filtered, "filter_count": _active_count(request), "clear_url": _clear_url(request),
    }
