from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMultiAlternatives
from django.template import loader, TemplateDoesNotExist


class EmailManager(object):
    @staticmethod
    def send_mail(recipient, template_prefix, subject, data=None, attachments=[], request=None):
        # template
        try:
            t = loader.get_template(f'{template_prefix}.txt')
        except TemplateDoesNotExist:
            t = None

        # HTML template
        try:
            t_html = loader.get_template(f'{template_prefix}.html')
        except TemplateDoesNotExist:
            t_html = None

        # recipients
        recipient_list = [recipient if isinstance(recipient, str) else recipient.email]

        site = get_current_site(request)

        # context
        context = {
            'recipient': recipient,
            'subject': subject,
            'request': request,
            'site': site,
            'settings': settings
        }

        if data:
            context.update(data)

        # message
        message = t.render(context) if t else ''
        html_message = t_html.render(context) if t_html else ''

        # message
        email = EmailMultiAlternatives(
            subject=subject,
            body=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipient_list,
        )
        email.attach_alternative(html_message, "text/html")

        # attachments
        for attachment in attachments:
            email.attach(attachment['filename'], attachment['content'], attachment['content_type'])

        if getattr(settings, 'MAILS_QUEUE', None):
            from pragmatic.jobs import send_mail_in_background
            send_mail_in_background.delay(email)
        else:
            email.send()