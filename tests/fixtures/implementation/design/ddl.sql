-- postgresql 18 / pack inventory 0.1.23 / rules normalize-v7 / lexicon c02847ddf0d7f18d159b00e4fe3673a4d638ab74ae8ce487388b06fd258e1d09 / generator ddl-v2

CREATE TABLE "wrhs_dsctn" (
  "sn" numeric(10,0) NOT NULL,
  "wrhs_qty" numeric(10,3),
  "wrhs_no" varchar(50) NOT NULL,
  "item_cd" varchar(10) NOT NULL,
  PRIMARY KEY ("wrhs_no", "sn")
);

CREATE TABLE "wrhus" (
  "wrhus_cd" varchar(10) NOT NULL,
  "wrhus_nm" varchar(200),
  PRIMARY KEY ("wrhus_cd")
);

CREATE TABLE "wrhs" (
  "wrhs_no" varchar(50) NOT NULL,
  "wrhs_ymd" char(8),
  "wrhus_cd" varchar(10) NOT NULL,
  PRIMARY KEY ("wrhs_no")
);

CREATE TABLE "item" (
  "item_cd" varchar(10) NOT NULL,
  "item_nm" varchar(100),
  PRIMARY KEY ("item_cd")
);

ALTER TABLE "wrhs_dsctn" ADD FOREIGN KEY ("item_cd") REFERENCES "item" ("item_cd");

ALTER TABLE "wrhs" ADD FOREIGN KEY ("wrhus_cd") REFERENCES "wrhus" ("wrhus_cd");

ALTER TABLE "wrhs_dsctn" ADD FOREIGN KEY ("wrhs_no") REFERENCES "wrhs" ("wrhs_no");
