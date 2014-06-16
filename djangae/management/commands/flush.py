#!/usr/bin/env python
# -*- coding: utf-8 -*-


from django.core.management.commands.flush import Command as DjangoCommand

class Command(DjangoCommand):
    def __init__(self, *args, **kwargs):
        from djangae.boot import setup_datastore_stubs

        setup_datastore_stubs()

        super(Command, self).__init__(*args, **kwargs)


