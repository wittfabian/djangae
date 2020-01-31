
CACHES = {
    # We default to the database cache, at least until
    # there is a sensible caching alternative (or low MemoryStore latency)
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
    }
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        }
    },
    'handlers': {
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler'
        }
    },
    'loggers': {
        'django.request': {
            'handlers': ['mail_admins'],
            'level': 'ERROR',
            'propagate': True,
        },
        'djangae': {
            'level': 'WARN'
        }
    }
}

# Setting to * is OK, because GAE takes care of domain routing - setting it to anything
# else just causes unnecessary pain when something isn't accessible under a custom domain
ALLOWED_HOSTS = ("*",)


# This is the model returned by djangae.config.get_app_config_model()
# In your project, you should set the SECRET_KEY setting by using
# SECRET_KEY = get_app_config(DJANGAE_APP_CONFIG_MODEL).secret_key
# to prevent a circular import
DJANGAE_APP_CONFIG_MODEL = "djangae.AppConfig"
