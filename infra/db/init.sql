-- Runs once, when the db volume is first created.
-- A separate database for pytest so tests never touch dev data.
CREATE DATABASE studysensei_test OWNER studysensei;
