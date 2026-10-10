/** Copilot tool: a technician's assigned appointments (by ServiceResource name or Id). READ-ONLY. */
global with sharing class FFCopilot_TechnicianSchedule {
    global class Request {
        @InvocableVariable(required=true label='Technician name or ServiceResource Id'
            description='A ServiceResource (technician) name or its 18-char Id.')
        global String technician;
    }
    global class Row {
        @InvocableVariable global String appointmentNumber;
        @InvocableVariable global String status;
        @InvocableVariable global Datetime scheduledStart;
    }

    @InvocableMethod(label='Get technician schedule'
        description='List the field-service appointments assigned to a technician (by ServiceResource name or Id), soonest first. Use this to answer what a technician is working on or to see their schedule.')
    global static List<Row> run(List<Request> requests) {
        List<Row> rows = new List<Row>();
        for (Request req : requests) {
            Id resourceId = null;
            try { resourceId = (Id) req.technician; } catch (Exception e) { /* it's a name */ }
            if (resourceId == null) {
                List<ServiceResource> rs =
                    [SELECT Id FROM ServiceResource WHERE Name = :req.technician LIMIT 1];
                if (!rs.isEmpty()) resourceId = rs[0].Id;
            }
            if (resourceId == null) continue;
            for (AssignedResource ar : [SELECT ServiceAppointment.AppointmentNumber,
                    ServiceAppointment.Status, ServiceAppointment.SchedStartTime
                    FROM AssignedResource WHERE ServiceResourceId = :resourceId
                    ORDER BY ServiceAppointment.SchedStartTime ASC NULLS LAST LIMIT 50]) {
                Row r = new Row();
                r.appointmentNumber = ar.ServiceAppointment.AppointmentNumber;
                r.status = ar.ServiceAppointment.Status;
                r.scheduledStart = ar.ServiceAppointment.SchedStartTime;
                rows.add(r);
            }
        }
        return rows;
    }
}
