/**
 * FieldFlow AI — the at-risk record trigger's callout handler.
 *
 * WHAT: when a ServiceAppointment is marked at-risk (the ServiceAppointmentAtRisk trigger), this
 * POSTs the appointment to the orchestrator's /webhooks/sf/at-risk endpoint, which drops it on the
 * same RabbitMQ exchange /sim uses — so the recovery pipeline (graph, policy, RCS) is unchanged.
 *
 * WHY @future(callout=true): Salesforce forbids a synchronous HTTP callout from inside a trigger, so
 * the trigger hands the ids here and this runs just after, asynchronously, where callouts are allowed.
 *
 * AUTH: the endpoint URL + the shared-secret header live in the `FieldFlow` Named Credential (set up
 * once in the UI — see salesforce-trigger-and-rich-rcs.md). Apex just calls `callout:FieldFlow/...`;
 * the platform attaches the header, so no URL and no secret sit in this code or in git.
 *
 * PAYLOAD maps to app/events/source.py::platform_event_to_at_risk (it accepts these __c keys):
 *   WorkOrderId__c  = the parent WorkOrder's record Id (the case key / correlationId downstream).
 *   AppointmentId__c= AppointmentNumber (FieldFlowRest also resolves this to the record for reads).
 *   Reason__c       = the At_Risk_Reason__c picklist (defaults to technician_delay if blank).
 *   DelayMinutes__c = Delay_Minutes__c (0 if blank).
 *   EventUuid       = appointmentNumber + last-modified epoch — our idempotency key (NFR-2): the
 *                     same at-risk save maps to one event, so a double-save makes one case.
 */
public with sharing class FieldFlowAtRisk {
    @future(callout=true)
    public static void notify(Set<Id> appointmentIds) {
        List<ServiceAppointment> appts = [
            SELECT Id, AppointmentNumber, ParentRecordId, Status,
                   At_Risk_Reason__c, Delay_Minutes__c, LastModifiedDate
            FROM ServiceAppointment
            WHERE Id IN :appointmentIds
        ];
        for (ServiceAppointment sa : appts) {
            Map<String, Object> payload = new Map<String, Object>{
                'WorkOrderId__c'  => sa.ParentRecordId,
                'AppointmentId__c'=> sa.AppointmentNumber,
                'Reason__c'       => String.isBlank(sa.At_Risk_Reason__c)
                                       ? 'technician_delay' : sa.At_Risk_Reason__c,
                'DelayMinutes__c' => sa.Delay_Minutes__c == null ? 0 : sa.Delay_Minutes__c,
                'EventUuid'       => sa.AppointmentNumber + '-'
                                       + String.valueOf(sa.LastModifiedDate.getTime())
            };
            HttpRequest req = new HttpRequest();
            req.setEndpoint('callout:FieldFlow/webhooks/sf/at-risk');
            req.setMethod('POST');
            req.setHeader('Content-Type', 'application/json');
            req.setBody(JSON.serialize(payload));
            HttpResponse res = new Http().send(req);
            // Fail loud in the debug log (the golden rule) — the body names the exact 4xx reason.
            System.debug('FieldFlow at-risk ' + sa.AppointmentNumber + ' -> '
                         + res.getStatusCode() + ' ' + res.getBody());
        }
    }
}
