import os

# Ce fichier est chargé automatiquement par Pytest avant tous les autres tests.
# Il garantit que les variables d'environnement sont définies pour TOUS les tests.

os.environ["API_SECRET"] = "test_secret_key_at_least_32_characters_long_xyz"
os.environ["TURNSTILE_SECRET"] = "test_turnstile_secret"
os.environ["LEGACY_API_SECRET"] = "SUPER_SECRET_CHANGE_ME"
