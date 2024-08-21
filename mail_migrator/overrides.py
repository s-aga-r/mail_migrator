import frappe
from frappe.desk.doctype.notification_log.notification_log import (
	enqueue_create_notification,
	get_title,
	get_title_html,
)
from frappe.email.doctype.email_account.email_account import EmailAccount
from frappe.email.receive import SentEmailInInboxError


class CustomEmailAccount(EmailAccount):
	def receive(self):
		"""Called by scheduler to receive emails from this EMail account using POP3/IMAP."""

		if (self.service != "Frappe Mail") or (
			not frappe.db.get_single_value("Migrator Settings", "send_reply_notification", cache=True)
		):
			super().receive()

		exceptions = []
		inbound_mails = self.get_inbound_mails()
		for mail in inbound_mails:
			try:
				communication = mail.process()
				frappe.db.commit()
				# If email already exists in the system
				# then do not send notifications for the same email.
				if communication and mail.flags.is_new_communication:
					# notify all participants of this thread
					if self.enable_auto_reply:
						self.send_auto_reply(communication, mail)
			except SentEmailInInboxError:
				frappe.db.rollback()
			except Exception:
				frappe.db.rollback()
				try:
					self.log_error(title="EmailAccount.receive")
					if self.use_imap:
						self.handle_bad_emails(mail.uid, mail.raw_message, frappe.get_traceback())
					exceptions.append(frappe.get_traceback())
				except Exception:
					frappe.db.rollback()
				else:
					frappe.db.commit()
			else:
				frappe.db.commit()

		if exceptions:
			raise Exception(frappe.as_json(exceptions))


def set_email_account(doc, method=None):
	settings = frappe.get_cached_doc("Migrator Settings")

	if not settings.enabled:
		return

	if doc.reference_doctype and doc.reference_name:
		if doc.reference_doctype == "Newsletter":
			doc.email_account = settings.newsletter_email_account
		else:  # Doc Emails
			doc.email_account = settings.transactional_email_account
	elif doc.communication:  # Direct Communication
		doc.email_account = settings.transactional_email_account
	else:
		# No fast* way to identify between Comment and Welcome/Password Reset Email
		if "New Reply" in doc.message or "mentioned you in a comment" in doc.message:
			doc.email_account = settings.notification_email_account
		else:  # Welcome/Password Reset Email
			doc.email_account = settings.transactional_email_account


def notify_user(doc, method=None):
	"""Notify user when a reply is received on a linked document."""

	if not frappe.db.get_single_value("Migrator Settings", "enabled", cache=True):
		return

	if (
		doc.in_reply_to
		and doc.status == "Linked"
		and doc.sent_or_received == "Received"
		and doc.communication_medium == "Email"
		and doc.communication_type == "Communication"
		and (doc.reference_doctype and doc.reference_name)
	):
		sender_fullname = doc.sender_full_name or doc.sender
		title = get_title(doc.reference_doctype, doc.reference_name)
		recipient = frappe.db.get_value("Communication", doc.in_reply_to, "user")
		subject = frappe._("New Reply: From {0} on {1} {2}").format(
			frappe.bold(sender_fullname),
			frappe.bold(doc.reference_doctype),
			get_title_html(title),
		)
		notification_log = {
			"subject": subject,
			"email_content": doc.content,
			"document_type": doc.reference_doctype,
			"document_name": doc.reference_name,
		}

		enqueue_create_notification(recipient, notification_log)
