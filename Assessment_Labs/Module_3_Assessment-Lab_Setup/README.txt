Module 3 Assessment: candidate files
====================================
fw_policy_tester.py   Evaluates a firewall ruleset against sample traffic flows.
flawed_ruleset.csv    The ruleset left by the contractor (Section B).
flows_visible.csv     Ten sample flows with the expected result for each.

Your invigilator will show you how to start the tester. It needs Python 3 only.

Ruleset format (CSV, one rule per line, first line is the header):
  rule,action,src,dst,protocol,port
  action   ALLOW or DENY
  src/dst  Control, Supervisory, DMZ, Enterprise, Management, Quarantine, ANY
  protocol TCP, UDP, ICMP or ANY
  port     a number (502), a range (80-443) or ANY

Save your finished ruleset as my_ruleset.csv.
