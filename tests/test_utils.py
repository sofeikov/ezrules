from ezrules.backend.utils import conditional_decorator


# Dummy decorator for testing
def dummy_decorator(func):
    def wrapped(*args, **kwargs):
        return f"Decorated: {func(*args, **kwargs)}"

    return wrapped


# Function to be decorated
def sample_function():
    return "Original function"


def test_with_true_condition():
    decorated_func = conditional_decorator(True, dummy_decorator)(sample_function)
    assert (
        decorated_func() == "Decorated: Original function"
    ), "The function should be decorated when the condition is True."


def test_with_false_condition():
    undecorated_func = conditional_decorator(False, dummy_decorator)(sample_function)
    assert (
        undecorated_func() == "Original function"
    ), "The function should not be decorated when the condition is False."
