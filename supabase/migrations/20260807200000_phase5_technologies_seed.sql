-- Seed a starter vocabulary for company tech stack selection (Settings page). Company
-- tech stack is still free text under the hood for matching purposes (see
-- worker/matching/engine.py - it compares against the AI's free-text extraction, not a
-- controlled vocabulary), but the Settings UI picks from this list rather than a bare
-- text box, to reduce spelling-variant drift (e.g. "React" vs "react.js" vs "ReactJS").
insert into technologies (name) values
  ('Python'), ('JavaScript'), ('TypeScript'), ('Java'), ('Go'), ('C#'), ('PHP'),
  ('React'), ('Next.js'), ('Vue'), ('Angular'), ('Node.js'), ('Spring'), ('Django'),
  ('AWS'), ('Azure'), ('GCP'), ('Docker'), ('Kubernetes'),
  ('PostgreSQL'), ('MySQL'), ('MongoDB'), ('Redis'), ('Elasticsearch'),
  ('AI'), ('머신러닝'), ('딥러닝'), ('데이터분석'), ('빅데이터'),
  ('정보보안'), ('클라우드'), ('블록체인'), ('IoT')
on conflict (name) do nothing;
