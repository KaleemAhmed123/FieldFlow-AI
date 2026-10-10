/** Copilot tool: a customer's appointments (by Contact name or Id). READ-ONLY. */
global with sharing class FFCopilot_CustomerAppointments {
    global class Request {
        @InvocableVariable(required=true label='Customer name or Contact Id'
            description='A Contact name (e.g. "Kaleem Ahmed") or its 18-char Contact Id.')
        global String customer;
    }
    global class Row {
        @InvocableVariable global String appointmentNumber;
        @InvocableVariable global String status;
        @InvocableVariable global Datetime scheduledStart;
    }

    @InvocableMethod(label='Get customer appointments'
        description='List all field-service appointments for a given customer (by Contact name or Id), most recent first. Use this to answer what appointments a customer has or to review their service history.')
    global static List<Row> run(List<Request> requests) {
        List<Row> rows = new List<Row>();
        for (Request req : requests) {
            Id contactId = null;
            try { contactId = (Id) req.customer; } catch (Exception e) { /* it's a name */ }
            if (contactId == null) {
                List<Contact> cs = [SELECT Id FROM Contact WHERE Name = :req.customer LIMIT 1];
                if (!cs.isEmpty()) contactId = cs[0].Id;
            }
            if (contactId == null) continue;
            List<Id> woIds = new List<Id>();
            for (WorkOrder wo : [SELECT Id FROM WorkOrder WHERE ContactId = :contactId]) {
                woIds.add(wo.Id);
            }
            for (ServiceAppointment sa : [SELECT AppointmentNumber, Status, SchedStartTime
                    FROM ServiceAppointment WHERE ParentRecordId IN :woIds
                    ORDER BY SchedStartTime DESC NULLS LAST LIMIT 50]) {
                Row r = new Row();
                r.appointmentNumber = sa.AppointmentNumber;
                r.status = sa.Status;
                r.scheduledStart = sa.SchedStartTime;
                rows.add(r);
            }
        }
        return rows;
    }
}
