/**
 * FieldFlow AI — curated Apex tools for the admin COPILOT, exposed as a Salesforce Hosted MCP server.
 *
 * WHY this is separate from FieldFlowRest: FieldFlowRest is the DETERMINISTIC pipeline path (our Python
 * calls named endpoints; the LLM never picks them). THIS class is the AGENTIC path — the copilot's LLM
 * reads each @InvocableMethod's `description` and decides, on its own, which tool to call to answer an
 * admin's open-ended question. So the descriptions matter: they are the tool's "API docs for the AI".
 *
 * Expose it: Setup -> MCP Servers -> New -> Add Tools -> To Apex actions -> pick this class -> Activate.
 * Guardrail (build step 12): copilot tools here are READ-ONLY. Any write stays human-confirmed in our app.
 */
public with sharing class FieldFlowCopilotTools {

    // ---- Tool 1: appointment health -----------------------------------------------------------
    public class HealthRequest {
        @InvocableVariable(required=true
            label='Appointment number or Id'
            description='A ServiceAppointment AppointmentNumber like SA-0001, or its 18-char record Id.')
        public String appointmentId;
    }

    public class Health {
        @InvocableVariable public String appointmentId;
        @InvocableVariable public String status;
        @InvocableVariable public String customerName;
        @InvocableVariable public String assetModel;
        @InvocableVariable public String warranty;        // active | expired | unknown
        @InvocableVariable public Datetime scheduledStart;
        @InvocableVariable public String note;
    }

    @InvocableMethod(
        label='Get appointment health'
        description='Given a field-service ServiceAppointment number or Id, return its status, the customer name, the serviced asset and its warranty status, and the scheduled start time. Use this to answer questions about one specific appointment.')
    public static List<Health> getAppointmentHealth(List<HealthRequest> requests) {
        List<Health> results = new List<Health>();
        for (HealthRequest req : requests) {
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

    // ---- Tool 2: appointments needing attention -----------------------------------------------
    public class AttentionRequest {
        @InvocableVariable(
            label='Max results'
            description='How many appointments to return at most. Defaults to 10 if left blank.')
        public Integer limitCount;
    }

    public class Attention {
        @InvocableVariable public String appointmentNumber;
        @InvocableVariable public String status;
        @InvocableVariable public Datetime scheduledStart;
    }

    @InvocableMethod(
        label='Find appointments needing attention'
        description='List field-service ServiceAppointments that are still open (not Completed, Cancelled or Closed), soonest first. Use this when an admin asks what needs attention, what is pending, or which jobs are still open.')
    public static List<Attention> findAppointmentsNeedingAttention(List<AttentionRequest> requests) {
        Integer cap = (requests != null && !requests.isEmpty() && requests[0].limitCount != null)
            ? requests[0].limitCount : 10;
        List<Attention> results = new List<Attention>();
        for (ServiceAppointment sa : [
                SELECT AppointmentNumber, Status, SchedStartTime FROM ServiceAppointment
                WHERE Status NOT IN ('Completed', 'Cancelled', 'Closed')
                ORDER BY SchedStartTime ASC NULLS LAST LIMIT :cap]) {
            Attention a = new Attention();
            a.appointmentNumber = sa.AppointmentNumber;
            a.status = sa.Status;
            a.scheduledStart = sa.SchedStartTime;
            results.add(a);
        }
        return results;
    }
}
