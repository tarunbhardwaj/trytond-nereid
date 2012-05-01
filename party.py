# -*- coding: UTF-8 -*-
'''
    nereid_trytond.party

    Partner Address is also considered as the login user

    :copyright: (c) 2010 by Sharoon Thomas.
    :copyright: (c) 2010-2012 by Openlabs Technologies & Consulting (P) Ltd.
    :license: GPLv3, see LICENSE for more details
'''
import random
import string
import hashlib

from wtforms import Form, TextField, IntegerField, SelectField, validators, \
    PasswordField
from wtfrecaptcha.fields import RecaptchaField
from werkzeug import redirect, abort

from nereid import request, url_for, render_template, login_required, flash
from nereid.globals import session, current_app
from trytond.model import ModelView, ModelSQL, fields
from trytond.pyson import Eval, Bool, Not
from trytond.transaction import Transaction
from trytond.config import CONFIG

from .i18n import _, get_translations


class RegistrationForm(Form):
    "Simple Registration form"

    def _get_translations(self):
        """
        Provide alternate translations factory.
        """
        return get_translations()

    name = TextField(_('Name'), [validators.Required(),])
    email = TextField(_('e-mail'), [validators.Required(), validators.Email()])
    password = PasswordField(_('New Password'), [
        validators.Required(),
        validators.EqualTo('confirm', message=_('Passwords must match'))])
    confirm = PasswordField(_('Confirm Password'))

    if 're_captcha_public' in CONFIG.options:
        captcha = RecaptchaField(
            public_key=CONFIG.options['re_captcha_public'], 
            private_key=CONFIG.options['re_captcha_private'], 
            secure=True
        )


class AddressForm(Form):
    """
    A form resembling the party.address
    """
    def _get_translations(self):
        """
        Provide alternate translations factory.
        """
        return get_translations()

    name = TextField(_('Name'), [validators.Required(),])
    street = TextField(_('Street'), [validators.Required(),])
    streetbis = TextField(_('Street (Bis)'))
    zip = TextField(_('Post Code'), [validators.Required(),])
    city = TextField(_('City'), [validators.Required(),])
    country = SelectField(_('Country'), [validators.Required(),], coerce=int)
    subdivision = IntegerField(_('State/County'), [validators.Required()])
    email = TextField(_('Email'))
    phone = TextField(_('Phone'))


class NewPasswordForm(Form):
    """
    Form to set a new password
    """
    def _get_translations(self):
        """
        Provide alternate translations factory.
        """
        return get_translations()

    password = PasswordField(_('New Password'), [
        validators.Required(),
        validators.EqualTo('confirm', message=_('Passwords must match'))])
    confirm = PasswordField(_('Repeat Password'))


class ChangePasswordForm(NewPasswordForm):
    """
    Form to change the password
    """
    def _get_translations(self):
        """
        Provide alternate translations factory.
        """
        return get_translations()

    old_password = PasswordField(_('Old Password'), [validators.Required()])


STATES = {
    'readonly': Not(Bool(Eval('active'))),
}


# pylint: disable-msg=E1101
class AdditionalDetails(ModelSQL, ModelView):
    "Additional Details for Address"
    _name = "address.additional_details"
    _description = __doc__
    _rec_name = 'value'
    
    def get_types(self):
        """
        Wrapper to convert _get_types dictionary 
        into a `list of tuple` for the use of Type Selection field
        
        This hook will scan all methods which start with _type_address_extend
        
        Your hook extension should look like:
                
        def _type_address_extend_<name>(self, cursor, user, context=None):
            return {
                        '<name>': '<value>'
            }
        
        An example from ups:
        
        return {'type': 'value'
            }
        
        :return: the list of tuple for Selection field
        """
        type_dict = {}
        for attribute in dir(self):
            if attribute.startswith('_type_address_extend'):
                type_dict.update(getattr(self, attribute).__call__())
        return type_dict.items()

    type = fields.Selection(
        'get_types', 'Type', required=True, states=STATES, select=1
    )
    value = fields.Char('Value', select=1, states=STATES)
    comment = fields.Text('Comment', states=STATES)
    address = fields.Many2One('party.address', 'Address', required=True,
        ondelete='CASCADE', states=STATES, select=1)
    active = fields.Boolean('Active', select=1)
    sequence = fields.Integer('Sequence')

    def default_active(self):
        return True
        
    def _type_address_extend_default(self):
        return {
            'dob': 'Date of Birth',
            'other': 'Other',
        }
    
AdditionalDetails()


class Address(ModelSQL, ModelView):
    """An address is considered as the equivalent of a user
    in a conventional Web application. Hence, the username and
    password are stored against the party.address object.
    """
    _name = 'party.address'

    registration_form = RegistrationForm

    #: Extra fields to cater to extended registration
    #: This field is retained only for legacy purposes.
    #: Additional details is now directly stored on the user object
    additional_details = fields.One2Many(
        'address.additional_details', 
        'address', 'Additional Details', states=STATES
    )
    email = fields.Char('Email')
    phone = fields.Char('Phone')

    @login_required
    def edit_address(self, address=None):
        """
        Create/Edit an Address

        POST will create a new address or update and existing address depending
        on the value of address.
        GET will return a new address/existing address edit form

        :param address: ID of the address
        """
        form = AddressForm(request.form, name=request.nereid_user.name)
        countries = [
            (c.id, c.name) for c in request.nereid_website.countries
            ]
        form.country.choices = countries
        if address not in (a.id for a in request.nereid_user.party.addresses):
            address = None
        if request.method == 'POST' and form.validate():
            if address is not None:
                self.write(address, {
                    'name': form.name.data,
                    'street': form.street.data,
                    'streetbis': form.streetbis.data,
                    'zip': form.zip.data,
                    'city': form.city.data,
                    'country': form.country.data,
                    'subdivision': form.subdivision.data,
                    'email': form.email.data,
                    'phone': form.phone.data,
                    })
            else:
                self.create({
                    'name': form.name.data,
                    'street': form.street.data,
                    'streetbis': form.streetbis.data,
                    'zip': form.zip.data,
                    'city': form.city.data,
                    'country': form.country.data,
                    'subdivision': form.subdivision.data,
                    'party': request.nereid_user.party.id,
                    'email': form.email.data,
                    'phone': form.email.data,
                    })
            return redirect(url_for('party.address.view_address'))
        elif request.method == 'GET' and address:
            # Its an edit of existing address, prefill data
            record = self.browse(address)
            form = AddressForm(
                name=record.name,
                street=record.street,
                streetbis=record.streetbis,
                zip=record.zip,
                city=record.city,
                country=record.country.id,
                subdivision=record.subdivision.id,
                email=record.email,
                phone=record.phone
            )
            form.country.choices = countries
        return render_template('address-edit.jinja', form=form, address=address)

    @login_required
    def view_address(self):
        "View the addresses of user"
        return render_template('address.jinja')

Address()


class NereidUser(ModelSQL, ModelView):
    """
    Nereid Users
    
    The Users were address records in versions before 0.3

    .. versionadded:: 0.3
    """
    _name = "nereid.user"
    _description = __doc__
    _inherits = {"party.party": 'party'}

    party = fields.Many2One('party.party', 'Party', required=True,
            ondelete='CASCADE', select=1)

    #: The email of the user is also the login name/username of the user
    email = fields.Char("e-Mail", select=1)

    #: The password is the user password + the salt, which is
    #: then hashed together
    password = fields.Sha('Password')

    #: The salt which was used to make the hash is separately
    #: stored. Needed for 
    salt = fields.Char('Salt', size=8)

    #: A unique activation code required to match the user's request
    #: for activation of the account.
    activation_code = fields.Char('Unique Activation Code')

    # The company of the website(s) to which the user is affiliated. This 
    # allows websites of the same company to share authentication/users. It 
    # does not make business or technical sense to have website of multiple
    # companies share the authentication.
    #
    # .. versionchanged:: 0.3
    #     Company is mandatory
    company = fields.Many2One('company.company', 'Company', required=True)

    def default_company(self):
        return Transaction().context.get('company') or False

    def __init__(self):
        super(NereidUser, self).__init__()
        self._sql_constraints += [
            ('unique_email_company', 'UNIQUE(email, company)',
                'Email must be unique in a company'),
            ]

    def _activate(self, user_id, activation_code):
        """
        Activate the User account

        .. note::
            This method will raise an assertion error if the activation_code is
            not valid.

        :param user_id: ID of the user
        :param activation_code: The activation code used
        :return: True if the activation code was correct
        """
        user = self.browse(user_id)
        assert user.activation_code == activation_code, \
                    'Invalid Activation Code'
        return self.write(user.id, {'activation_code': False})

    def get_registration_form(self):
        """
        Returns a registration form for use in the site

        .. tip::

            Configuration of re_captcha

            Remember to forward X-Real-IP in the case of Proxy servers

        """
        # Add re_captcha if the configuration has such an option
        if 're_captcha_public' in CONFIG.options:
            registration_form = RegistrationForm(
                request.form, captcha={'ip_address': request.remote_addr}
            )
        else:
            registration_form = RegistrationForm(request.form)

        return registration_form

    def registration(self):
        """
        Invokes registration of an user
        """
        registration_form = self.get_registration_form()

        if request.method == 'POST' and registration_form.validate():
            existing = self.search([
                ('email', '=', request.form['email']),
                ('company', '=', request.nereid_website.company.id),
                ])
            if existing:
                flash(_('A registration already exists with this email. '
                    'Please contact customer care')
                )
            else:
                user_id = self.create({
                    'name': registration_form.name.data,
                    'email': registration_form.email.data,
                    'password': registration_form.password.data,
                    })
                self.create_act_code(user_id)
                flash(
                    _('Registration Complete. Check your email for activation')
                )
                return redirect(
                    request.args.get('next', url_for('nereid.website.home'))
                )

        return render_template('registration.jinja', form=registration_form)

    @login_required
    def change_password(self):
        """
        Changes the password

        .. tip::
            On changing the password, the user is logged out and the login page
            is thrown at the user
        """
        form = ChangePasswordForm(request.form)

        if request.method == 'POST' and form.validate():
            user = request.nereid_user

            # Confirm the current password
            password = form.old_password.data
            password += user.salt or ''
            if isinstance(password, unicode):
                password = password.encode('utf-8')
            password_sha = hashlib.sha1(password).hexdigest()

            if password_sha == user.password:
                self.write(
                    request.nereid_user.id, 
                    {'password': form.password.data}
                )
                flash(
                    _('Your password has been successfully changed! '
                    'Please login again')
                )
                session.pop('user')
                return redirect(url_for('nereid.website.login'))
            else:
                flash(_("The current password you entered is invalid"))
        
        return render_template(
            'change-password.jinja', change_password_form=form
        )

    @login_required
    def new_password(self):
        """Create a new password
        
        .. tip::

            Unlike change password this does not demand the old password. 
            And hence this method will check in the session for a parameter 
            called allow_new_password which has to be True. This acts as a 
            security against attempts to POST to this method and changing 
            password.

            The allow_new_password flag is popped on successful saving

        This is intended to be used when a user requests for a password reset.
        """
        form = NewPasswordForm(request.form)

        if request.method == 'POST' and form.validate():
            if not session.get('allow_new_password', False):
                current_app.logger.debug('New password not allowed in session')
                abort(403)

            self.write(
                request.nereid_user.id, 
                {'password': form.password.data}
            )
            session.pop('allow_new_password')
            flash(_('Your password has been successfully changed! '
                'Please login again')
            )
            session.pop('user')
            return redirect(url_for('nereid.website.login'))

        return render_template('new-password.jinja', password_form=form)

    def activate(self, user_id, activation_code):
        """A web request handler for activation

        :param activation_code: A 12 character activation code indicates reset
            while 16 character activation code indicates a new registration
        """
        try:
            self._activate(user_id, activation_code)
        except AssertionError:
            flash(_('Invalid Activation Code'))
        else:
            # Log the user in since the activation code is correct
            session['user'] = user_id

            # Redirect the user to the correct location according to the type
            # of activation code.
            if len(activation_code) == 12:
                session['allow_new_password'] = True
                return redirect(url_for('nereid.user.new_password'))
            elif len(activation_code) == 16:
                flash(_('Your account has been activated'))
                return redirect(url_for('nereid.website.home'))

        return redirect(url_for('nereid.website.login'))

    def create_act_code(self, user_id, code_type="new"):
        """Create activation code
            
        A 12 character activation code indicates reset while 16 
        character activation code indicates a new registration
        
        :param user_id: ID of the User
        :param code_type:   "new" for new activation code
                            "reset" for resetting existing account
        """
        assert code_type in ("new", "reset")
        length = 16 if code_type == "new" else 12

        act_code = ''.join(
            random.sample(string.letters + string.digits, length)
        )
        return self.write(user_id, {'activation_code': act_code})

    def reset_account(self):
        """
        Reset the password for the user. 

        .. tip::
            This does NOT reset the password, but just creates an activation
            code and sends the link to the email of the user. If the user uses
            the link, he can change his password.
        """
        if request.method == 'POST':
            user_ids = self.search([
                ('email', '=', request.form['email']),
                ('company', '=', request.nereid_website.company.id),
                ])

            if not user_ids:
                flash(_('Invalid email address'))
                return render_template('reset-password.jinja')

            self.create_act_code(user_ids[0], "reset")
            flash(_('An email has been sent to your account for resetting'
                ' your credentials'))
            return redirect(url_for('nereid.website.login'))

        return render_template('reset-password.jinja')

    def authenticate(self, email, password):
        """Assert credentials and if correct return the
        browse record of the user

        :param email: email of the user
        :param password: password of the user
        :return:
            Browse Record: Successful Login
            None: User cannot be found or wrong password
            False: Account is inactive
        """

        user_ids = self.search([
            ('email', '=', request.form['email']),
            ('company', '=', request.nereid_website.company.id),
            ])

        if not user_ids:
            current_app.logger.debug("No user with email %s" % email)
            return None

        if len(user_ids) > 1:
            current_app.logger.debug('%s has too many accounts' % email)
            return None

        user = self.browse(user_ids[0])
        if user.activation_code and len(user.activation_code) == 16:
            # A new account with activation pending
            current_app.logger.debug('%s not activated' % email)
            flash(_("Your account has not been activated yet!"))
            return False # False so to avoid `invalid credentials` flash

        password += user.salt or ''

        if isinstance(password, unicode):
            password = password.encode('utf-8')

        password_sha = hashlib.sha1(password).hexdigest()
        if password_sha == user.password:
            # Reset any reset activation code that might be there since its a 
            # successful login with the old password
            if user.activation_code:
                self.write(user.id, {'activation_code': False})
            return user

        return None

    def _convert_values(self, values):
        """
        A helper method which looks if the password is specified in the values.
        If it is, then the salt is also made and added

        :param values: A dictionary of field: value pairs
        """
        if 'password' in values and values['password']:
            values['salt'] = ''.join(random.sample(
                string.ascii_letters + string.digits, 8))
            values['password'] += values['salt']
        return values

    def create(self, values):
        """
        Create, but add salt before saving

        :param values: Dictionary of Values
        """
        return super(NereidUser, self).create(self._convert_values(values))

    def write(self, ids, values):
        """
        Update salt before saving

        :param ids: IDs of the records
        :param values: Dictionary of values
        """
        return super(NereidUser, self).write(ids, self._convert_values(values))


NereidUser()


class EmailTemplate(ModelSQL, ModelView):
    'add `url_for` to the template context'
    _name = 'electronic_mail.template'

    def template_context(self, record):
        context = super(EmailTemplate, self).template_context(record)
        context['url_for'] = url_for
        return context

EmailTemplate()
