def conditional_auth(condition, decorator):
    def wrapper(func):
        if condition:
            return decorator(func)
        return func

    return wrapper
