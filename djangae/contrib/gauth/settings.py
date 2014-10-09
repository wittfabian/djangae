
AUTHENTICATION_BACKENDS = (
    'djangae.contrib.auth.backends.AppEngineUserAPI',
)

AUTH_USER_MODEL = 'djangae.User'
LOGIN_URL = 'djangae_login_redirect'
