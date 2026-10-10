/**
 * Copilot tool: appointment health. One @InvocableMethod per class (Salesforce allows only one).
 * READ-ONLY. The `description` is what the copilot LLM reads to decide when to call this.
 */
global with sharing class FFCopilot_AppointmentHealth {
    global class Request {
        @InvocableVariable(required=true label='Appointment number or Id'
            description='A ServiceAppointment AppointmentNumber like SA-0001, or its 18-char record Id.')
        global String appointmentId;
    }
    global class Health {
        @InvocableVariable global String appointmentId;
        @InvocableVariable global String status;
        @InvocableVariable global String customerName;
        @InvocableVariable global String assetModel;
        @InvocableVariable global String warranty;        // active | expired | unknown
        @InvocableVariable global Datetime scheduledStart;
        @InvocableVariable global String note;
    }

    @InvocableMethod(label='Get appointment health'
        description='Given a field-service ServiceAppointment number or Id, return its status, the customer name, the serviced asset and its warranty status, and the scheduled start time. Use this to answer questions about one specific appointment.')
    global static List<Health> run(List<Request> requests) {
        List<Health> results = new List<Health>();
        for (Request req : requests) {
            Health h = new Health();
            h.appointmentId = req.appointmentId;
            h.warranty = 'unknown';
            List<ServiceAppointment> rows = [
                SELECT Id, AppointmentNumber, Status, SchedStartTime, ParentRecordId
                FROM ServiceAppointment
                WHERE AppointmentNumber = :req.appointmentId OR Id = :req.appointmentId LIMIT 1];
            if (rows.isEmpty()) { h.note = 'not found'; results.add(h); continue; }
            ServiceAppointment sa = rows[0];
            h.status = sa.Status;
            h.scheduledStart = sa.SchedStartTime;
            try {
                WorkOrder wo = [SELECT ContactId, AssetId FROM WorkOrder
                                WHERE Id = :sa.ParentRecordId LIMIT 1];
                if (wo.ContactId != null) {
                    h.customerName = [SELECT Name FROM Contact WHERE Id = :wo.ContactId LIMIT 1].Name;
                }
                if (wo.AssetId != null) {
                    Asset a = [SELECT Name, Warranty_Active__c FROM Asset WHERE Id = :wo.AssetId LIMIT 1];
                    h.assetModel = a.Name;
                    h.warranty = a.Warranty_Active__c ? 'active' : 'expired';
                }
            } catch (Exception ignore) { /* parent not a WorkOrder / no access — leave fields null */ }
            results.add(h);
        }
        return results;
    }
}
