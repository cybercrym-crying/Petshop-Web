# OOP: PEWARISAN - induk semua error bisnis (CheckoutError, InvalidTransition,
# InsufficientStock mewarisi ini) sehingga view cukup `except PetshopError`.
class PetshopError(Exception):
    pass
