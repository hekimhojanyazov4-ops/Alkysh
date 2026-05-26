from django import template

register = library = template.Library()

@register.filter(name='get_attr')
def get_attr(obj, attr_name):
    """
    Template filter to get an attribute of an object dynamically.
    Usage: {{ object|get_attr:"attribute_name" }}
    """
    return getattr(obj, attr_name, None)

@register.simple_tag(takes_context=True)
def url_replace(context, **kwargs):
    query = context['request'].GET.copy()
    for kwarg, value in kwargs.items():
        query[kwarg] = value
    return query.urlencode()

@register.simple_tag(takes_context=True)
def url_replace_params(context, **kwargs):
    query = context['request'].GET.copy()
    for kwarg, value in kwargs.items():
        query[kwarg] = value
    return "&" + query.urlencode() if query else ""