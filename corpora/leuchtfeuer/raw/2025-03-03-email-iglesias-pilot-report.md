From: Tomás Iglesias <t.iglesias@gezeitenwerk.example>
To: Petra Vogelsang <p.vogelsang@blauwal-logistik.example>
Cc: LEUCHTFEUER steering committee <leuchtfeuer-la@blauwal-logistik.example>; Marek Duszek <m.duszek@blauwal-logistik.example>
Date: Mon, 3 Mar 2025 11:22:00 +0100
Subject: SEAGULL pilot cutover — vendor summary, week one

Dear Petra, dear committee,

A week has passed since the SEAGULL weekend, so here is Gezeitenwerk's summary while the details
are fresh — and let me start with the headline, because for once the headline is a pleasure to
write: the pilot cutover at Bremen-Walle is done, and it is a success!

The cutover ran over the weekend of 22–23 February exactly along the runbook. The data migration
completed inside its window on the first attempt — article masters, stock, and open orders all
reconciled against the KOMET extracts with zero unexplained differences, which those of you who
have lived through WMS migrations will know is not a sentence one gets to write often. The
BasaltDB stack behaved impeccably from the first minute; the decision to move the persistence
layer before the pilot, rather than after, paid for itself this weekend.

On availability: **order release at Walle stood still for only four hours over the whole cutover
weekend**, and Walle received trucks on Monday morning, 24 February, from 06:00 as planned. The first inbound wave was
processed on QUAYSTONE without a single escalation to the war room. Scanning throughput in week
one has been running above the plan values, and the pick error rate is well inside the corridor we
promised. I will not drown you in dashboards here — the full metrics pack goes to Jonas for the
project share today — but the shape of the curves is exactly what a healthy site looks like in its
first week.

Allow me one sentence of pride, clearly labelled as such: in my view this was the smoothest
mid-size WMS cutover we have delivered in years, and I have said so inside Gezeitenwerk where the
compliments actually change behaviour — the implementation crew that sat in Walle over that
weekend deserves them. Jörn's team met them more than halfway; a cutover goes like this only when
the site wants it to.

What remains, so this mail is not only sunshine: the hypercare crew stays on site for two weeks as
agreed, three low-priority defects from the weekend are in the tracker with fixes scheduled inside
hypercare, and the label-printing interface needs one configuration follow-up for a carrier format
that appears only in month-end volumes — we will have it in place well before month-end, and it is
being tested against a recorded batch, not live traffic.

From the vendor side, nothing stands in the way of the hold-point review in April. We are ready
to bring the lessons-learned workshop to Bremen in the last week of March if that suits the
committee's calendar — say the word and I will book the travel the same day! It would be a shame
to let lessons this fresh go cold in a drawer until the autumn.

With best regards from Hamburg — and my sincere congratulations to the whole Walle crew,

Tomás

Tomás Iglesias
Account Manager, Gezeitenwerk Software GmbH
