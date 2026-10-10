/** Copilot tool: open appointments with no technician assigned. READ-ONLY. */
global with sharing class FFCopilot_Unassigned {
    global class Request {
        @InvocableVariable(label='Max results' description='How many to return at most (default 10).')
        global Integer limitCount;
    }
    global class Row {
        @InvocableVariable global String appointmentNumber;
        @InvocableVariable global String status;
        @InvocableVariable global Datetime scheduledStart;
    }

    @InvocableMethod(label='Find unassigned appointments'
        description='List open field-service appointments that have NO technician assigned yet, soonest first. Use this to answer which jobs still need a technician or what is unassigned.')
    global static List<Row> run(List<Request> requests) {
        Integer cap = (requests != null && !requests.isEmpty() && requests[0].limitCount != null)
            ? requests[0].limitCount : 10;
        List<Row> rows = new List<Row>();
        for (ServiceAppointment sa : [SELECT AppointmentNumber, Status, SchedStartTime
                FROM ServiceAppointment
                WHERE Status NOT IN ('Completed', 'Cancelled', 'Closed')
                  AND Id NOT IN (SELECT ServiceAppointmentId FROM AssignedResource)
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
