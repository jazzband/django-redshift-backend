# -*- coding: utf-8 -*-


DATABASES = {
    'default': {
        'ENGINE': 'django_redshift_backend',
        'NAME': 'testing',
        'USER': 'user',
        'PASSWORD': 'password',
        'HOST': 'localhost',
        'PORT': '5439',
        'OPTIONS': {
            'query_group': 'webapp',
        },
    }
}

SECRET_KEY = '<key>'
