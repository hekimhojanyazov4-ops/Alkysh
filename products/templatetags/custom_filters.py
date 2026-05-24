from django import template

register = template.Library()

@register.simple_tag(takes_context=True)
def url_replace(context, key, value):
    request = context['request']
    params = request.GET.copy()
    params = request.GET.copy() # Get a mutable copy of the current GET parameters
    params[key] = value
    return '?' + params.urlencode()

@register.simple_tag(takes_context=True)
def url_replace_params(context, key, value):
    request = context['request']
    params = request.GET.copy()
    params[key] = value
    return '?' + params.urlencode()