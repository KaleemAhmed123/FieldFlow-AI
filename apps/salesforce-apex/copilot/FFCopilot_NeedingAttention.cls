/** Copilot tool: open appointments needing attention. READ-ONLY. One @InvocableMethod per class. */
global with sharing class FFCopilot_NeedingAttention {
    global class Request {
        @InvocableVariable(label='Max results' description='How many to return at most (default 10).')
        global Integer limitCount;
    }
    global class Row {
        @InvocableVariable global String appointmentNumber;
        @InvocableVariable global String status;
        @InvocableVariable global Datetime scheduledStart;
    }

    @InvocableMethod(label='Find appointments needing attention'
        description='List field-service ServiceAppointments that are still open (not Completed, Cancelled or Closed), soonest first. Use this when an admin asks what needs attention, what is pending, or which jobs are still open.')
    global static List<Row> run(List<Request> requests) {
        Integer cap = (requests != null && !requests.isEmpty() && requests[0].limitCount != null)
            ? requests[0].limitCount : 10;
        List<Row> rows = new List<Row>();
        for (ServiceAppointment sa : [SELECT AppointmentNumber, Status, SchedStartTime
                FROM ServiceAppointment WHERE Status NOT IN ('Completed', 'Cancelled', 'Closed')
                ORDER BY SchedStartTime ASC NULLS LAST LIMIT :cap]) {
            Row r = new Row();
            r.appointmentNumber = sa.AppointmentNumber;
            r.status = sa.Status;
            r.scheduledStart = sa.SchedStartTime;
            rows.add(r);
        }
        return rows;
    }
}
