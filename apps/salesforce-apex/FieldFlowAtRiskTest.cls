/**
 * Coverage + contract check for the at-risk trigger → callout path.
 *
 * Salesforce won't let a callout run in a test for real, so we install an HttpCalloutMock: it asserts
 * the request goes to the right Named-Credential endpoint with the expected JSON, and returns a fake
 * 200. Ticking At_Risk__c inside Test.start/stopTest drives the trigger → the @future runs at
 * stopTest against the mock. If the callout didn't fire, no mock response is recorded and the test
 * fails on the assert count.
 */
@isTest
private class FieldFlowAtRiskTest {
    private static Integer calls = 0;

    private class Mock implements HttpCalloutMock {
        public HttpResponse respond(HttpRequest req) {
            calls++;
            System.assertEquals('callout:FieldFlow/webhooks/sf/at-risk', req.getEndpoint(),
                'callout must target the FieldFlow Named Credential endpoint');
            Map<String, Object> body =
                (Map<String, Object>) JSON.deserializeUntyped(req.getBody());
            System.assertEquals('part_missing', body.get('Reason__c'), 'reason passed through');
            System.assert(body.containsKey('AppointmentId__c'), 'appointment id present');
            HttpResponse res = new HttpResponse();
            res.setStatusCode(200);
            res.setBody('{"published":true}');
            return res;
        }
    }

    @isTest
    static void fires_callout_when_marked_at_risk() {
        ServiceAppointment sa = new ServiceAppointment(
            Subject = 'FFTest',
            EarliestStartTime = System.now(),
            DueDate = System.now().addHours(4)
        );
        insert sa;

        Test.setMock(HttpCalloutMock.class, new Mock());
        Test.startTest();
        sa.At_Risk__c = true;
        sa.At_Risk_Reason__c = 'part_missing';
        update sa;
        Test.stopTest();

        System.assertEquals(1, calls, 'exactly one at-risk callout should have fired');
    }
}
