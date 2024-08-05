import frappe
from frappe.desk.doctype.notification_log.notification_log import (
	enqueue_create_notification,
	get_title,
	get_title_html,
)


def notify_user(doc, method=None):
	"""Notify user when a reply is received on a linked document."""

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
