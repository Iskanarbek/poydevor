from django.contrib import admin

from architects.models import ArchitectProfile, PortfolioImage, PortfolioProject, Skill, Style


class PortfolioImageInline(admin.TabularInline):
    model = PortfolioImage
    extra = 1


class PortfolioProjectInline(admin.TabularInline):
    model = PortfolioProject
    extra = 0


@admin.register(ArchitectProfile)
class ArchitectProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "rating", "completed_projects_count"]
    inlines = [PortfolioProjectInline]


@admin.register(PortfolioProject)
class PortfolioProjectAdmin(admin.ModelAdmin):
    inlines = [PortfolioImageInline]


admin.site.register(Style)
admin.site.register(Skill)
