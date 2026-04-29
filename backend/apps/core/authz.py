from functools import wraps

from django.http import JsonResponse


def user_has_any_role(user, roles):
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=roles).exists()


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not user_has_any_role(request.user, roles):
                return JsonResponse({"error": "forbidden"}, status=403)
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
