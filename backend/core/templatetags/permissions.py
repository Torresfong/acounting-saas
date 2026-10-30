from django import template

from core import permissions

register = template.Library()


@register.simple_tag(takes_context=True)
def can(context, action, company):
    """`{% can "invite_staff" company as allowed %}`: the same check the views use."""
    return permissions.can(context["request"].user, action, company)
