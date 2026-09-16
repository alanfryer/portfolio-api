CREATE TABLE IF NOT EXISTS "users" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT,
    "username" VARCHAR NOT NULL,
    "hashed_password" VARCHAR NOT NULL
);

-- Ensure usernames remain globally unique and lookups are fast
CREATE UNIQUE INDEX IF NOT EXISTS "ix_users_username" ON "users" ("username");
CREATE INDEX IF NOT EXISTS "ix_users_id" ON "users" ("id");


CREATE TABLE IF NOT EXISTS "roles" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT,
    "user_id" INTEGER NOT NULL,
    "role_name" VARCHAR NOT NULL,
    FOREIGN KEY ("user_id") REFERENCES "users" ("id") ON DELETE CASCADE
);

-- Indexing for optimized relational lookups and joins
CREATE INDEX IF NOT EXISTS "ix_roles_id" ON "roles" ("id");

-- Table Structure
CREATE TABLE IF NOT EXISTS stocks (
    symbol TEXT PRIMARY KEY,
    company TEXT NOT NULL,
    exchange TEXT NOT NULL,
    currency TEXT NOT NULL,
    owned INTEGER NOT NULL,
    cost REAL NOT NULL
);

-- Insert Statements
INSERT INTO portfolio(symbol, company, exchange, currency, owned, cost) VALUES
('AZN.L', 'AstraZeneca plc', 'LSE', 'GBP', 62, 7378.22),
('BA.L', 'BAE Systems plc', 'LSE', 'GBP', 148, 2952.29),
('BARC.L', 'Barclays plc', 'LSE', 'GBP', 1533, 7745.54),
('BP.L', 'BP plc', 'LSE', 'GBP', 94, 470.16),
('BATS.L', 'British American Tobacco plc', 'LSE', 'GBP', 95, 4418.95),
('BT-A.L', 'BT Group plc', 'LSE', 'GBP', 756, 1539.21),
('CCH.L', 'Coca-Cola HBC plc', 'LSE', 'GBP', 22, 1088.20),
('CPG.L', 'Compass Group plc', 'LSE', 'USD', 212, 4868.96),
('DPLM.L', 'Diploma plc', 'LSE', 'GBP', 15, 1074.56),
('GSK.L', 'Glaxosmithkline plc', 'LSE', 'GBP', 179, 3465.16),
('GLEN.L', 'Glencore plc', 'LSE', 'GBP', 1478, 8158.84),
('HLMA.L', 'Halma plc', 'LSE', 'GBP', 34, 1252.76),
('HSBA.L', 'HSBC Holdings plc', 'LSE', 'GBP', 1597, 24371.59),
('IGG.L', 'IG Group Holdings plc', 'LSE', 'GBP', 158, 2465.43),
('IHG', 'Intercontinental Hotels Group (IHG)', 'NYSE', 'USD', 1, 179.71),
('LLOY.L', 'Lloyds Banking Group plc', 'LSE', 'GBP', 5584, 6266.31),
('LSEG.L', 'London Stock Exchange Group plc', 'LSE', 'GBP', 66, 5672.97),
('NG.L', 'National Grid plc', 'LSE', 'GBP', 245, 3031.46),
('NWG.L', 'Natwest Group plc', 'LSE', 'GBP', 773, 5341.72),
('NXT.L', 'Next plc', 'LSE', 'GBP', 12, 1877.74),
('PRU.L', 'Prudential plc', 'LSE', 'GBP', 185, 2032.55),
('REL.L', 'RELX plc', 'LSE', 'GBP', 122, 3096.57),
('RTO.L', 'Rentokil Initial plc', 'LSE', 'GBP', 874, 3014.23),
('RIO.L', 'Rio Tinto plc', 'LSE', 'GBP', 122, 8661.17),
('RR.L', 'Rolls-Royce Holdings plc', 'LSE', 'GBP', 55, 791.96),
('SMT.L', 'Scottish Mortgage Investment Trust plc', 'LSE', 'GBP', 39, 527.17),
('SHEL.L', 'Shell plc', 'LSE', 'GBP', 35, 1054.36),
('SSE.L', 'SSE plc', 'LSE', 'GBP', 74, 1812.88),
('SDLF.L', 'Standard Life plc', 'LSE', 'GBP', 112, 1009.00),
('TSCO.L', 'Tesco plc', 'LSE', 'GBP', 506, 2408.24),
('ULVR.L', 'Unilever plc', 'LSE', 'GBP', 101, 4652.55);

