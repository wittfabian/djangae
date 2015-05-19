import re

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import (
    AbstractBaseUser,
    python_2_unicode_compatible,
    UserManager,
)
from django.core.mail import send_mail
from django.core import validators
from django.utils.http import urlquote
from django.db import models
from django.utils import timezone, six
from django.utils.translation import ugettext_lazy as _


class GaeUserManager(UserManager):

    def pre_create_google_user(self, email, **extra_fields):
        """ Pre-create a User object for a user who will later log in via Google Accounts. """
        values = dict(
            # defaults which can be overridden
            is_active=True,
        )
        values.update(**extra_fields)
        values.update(
            # things which cannot be overridden
            email=self.normalize_email(email),
            username=None,
            password=make_password(None), # unusable password
            # Stupidly, last_login is not nullable, so we can't set it to None.
        )
        return self.create(**values)


@python_2_unicode_compatible
class GaeAbstractBaseUser(AbstractBaseUser):
    """ Absract base class for creating a User model which works with the App
    Engine users API. """

    username = models.CharField(
        # This stores the Google user_id, or custom username for non-Google-based users.
        # We allow it to be null so that Google-based users can be pre-created before they log in.
        _('User ID'), max_length=21, unique=True, null=True, default=None,
        validators=[
            validators.RegexValidator(re.compile('^\d{21}$'), _('User Id should be 21 digits.'), 'invalid')
        ]
    )
    first_name = models.CharField(_('first name'), max_length=30, blank=True)
    last_name = models.CharField(_('last name'), max_length=30, blank=True)
    # The null-able-ness of the email is only to deal with when an email address moves between Google Accounts
    email = models.EmailField(_('email address'), unique=True, null=True)
    is_staff = models.BooleanField(
        _('staff status'), default=False,
        help_text=_('Designates whether the user can log into this admin site.')
    )
    is_active = models.BooleanField(
        _('active'), default=True,
        help_text=_(
            'Designates whether this user should be treated as '
            'active. Unselect this instead of deleting accounts.'
        )
    )
    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    objects = GaeUserManager()

    class Meta:
        abstract = True

    def get_absolute_url(self):
        return "/users/%s/" % urlquote(self.username)

    def get_full_name(self):
        """
        Returns the first_name plus the last_name, with a space in between.
        """
        full_name = '%s %s' % (self.first_name, self.last_name)
        return full_name.strip()

    def get_short_name(self):
        "Returns the short name for the user."
        return self.first_name

    def email_user(self, subject, message, from_email=None):
        """
        Sends an email to this User.
        """
        send_mail(subject, message, from_email, [self.email])

    def __str__(self):
        """
            We have to override this as username is nullable. We either return the email
            address, or if there is a username, we return "email (username)".
        """
        username = self.get_username()
        if username:
            return "{} ({})".format(six.text_type(self.email), six.text_type(username))
        return six.text_type(self.email)

