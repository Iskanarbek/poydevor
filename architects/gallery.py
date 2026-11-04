from architects.models import PortfolioProject, Style


def gallery_context(request):
    """The projects of every architect for the gallery (optionally one style), used by the
    clients' home page and by the public gallery page."""
    projects = (
        PortfolioProject.objects.visible()
        .select_related("architect__user", "architect__studio_owned", "style")
        .prefetch_related("images")
    )
    style_id = request.GET.get("style")
    if style_id and style_id.isdigit():
        projects = projects.filter(style_id=style_id)
    return {"projects": projects, "styles": Style.objects.all(), "selected_style": style_id}
