# -*- coding: utf-8 -*-


DATABASES = {
    'default': {
        'ENGINE': 'django_redshift_backend',
        'NAME': 'testing',
        'USER': 'user',
        'PASSWORD': 'password',
        'HOST': 'localhost',
        'PORT': '5439',
    }
}

SECRET_KEY = '<key>'
