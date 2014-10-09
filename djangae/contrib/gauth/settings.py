
AUTHENTICATION_BACKENDS = (
    'djangae.contrib.gauth.backends.AppEngineUserAPI',
)

AUTH_USER_MODEL = 'djangae.GaeDatastoreUser'
LOGIN_URL = 'djangae_login_redirect'
