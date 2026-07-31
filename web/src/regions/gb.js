/* United Kingdom · nations and regions → major towns and cities
 * Second level lists the largest towns and cities per region, not every civil parish —
 * anything else is typed in under "Other" (Munea honesty rule: no unverified region data).
 * coords = the region's main city, used for weather and air quality (Open-Meteo, worldwide).
 * Added 2026-07-31 after Edward chose per-country administrative lists. */
window.MUNEA_REGIONS = window.MUNEA_REGIONS || {};
window.MUNEA_REGIONS.GB = {
  countryCode: 'GB',
  tier1Key: 'profile.regionTier1Region',
  tier2Key: 'profile.regionTier2City',
  otherKey: 'profile.regionOther',
  regions: {
    'Greater London': { coords: [51.507, -0.128], cities: ['London', 'Croydon', 'Bromley', 'Barnet', 'Ealing', 'Enfield', 'Hounslow', 'Richmond upon Thames'] },
    'South East England': { coords: [50.827, -0.153], cities: ['Brighton', 'Southampton', 'Portsmouth', 'Reading', 'Oxford', 'Milton Keynes', 'Slough', 'Basingstoke', 'Canterbury'] },
    'South West England': { coords: [51.455, -2.587], cities: ['Bristol', 'Plymouth', 'Bournemouth', 'Swindon', 'Exeter', 'Gloucester', 'Bath', 'Torquay'] },
    'East of England': { coords: [52.205, 0.121], cities: ['Cambridge', 'Norwich', 'Ipswich', 'Luton', 'Peterborough', 'Southend-on-Sea', 'Colchester', 'Chelmsford'] },
    'East Midlands': { coords: [52.955, -1.150], cities: ['Nottingham', 'Leicester', 'Derby', 'Northampton', 'Lincoln', 'Chesterfield'] },
    'West Midlands': { coords: [52.486, -1.890], cities: ['Birmingham', 'Coventry', 'Wolverhampton', 'Stoke-on-Trent', 'Solihull', 'Worcester', 'Telford'] },
    'North West England': { coords: [53.481, -2.242], cities: ['Manchester', 'Liverpool', 'Bolton', 'Stockport', 'Preston', 'Blackpool', 'Warrington', 'Chester'] },
    'North East England': { coords: [54.978, -1.618], cities: ['Newcastle upon Tyne', 'Sunderland', 'Middlesbrough', 'Gateshead', 'Durham', 'Darlington'] },
    'Yorkshire and the Humber': { coords: [53.801, -1.549], cities: ['Leeds', 'Sheffield', 'Bradford', 'Hull', 'York', 'Doncaster', 'Huddersfield', 'Wakefield'] },
    'Scotland': { coords: [55.953, -3.189], cities: ['Edinburgh', 'Glasgow', 'Aberdeen', 'Dundee', 'Inverness', 'Perth', 'Stirling', 'Paisley'] },
    'Wales': { coords: [51.481, -3.179], cities: ['Cardiff', 'Swansea', 'Newport', 'Wrexham', 'Bangor', 'Barry'] },
    'Northern Ireland': { coords: [54.597, -5.930], cities: ['Belfast', 'Londonderry', 'Lisburn', 'Newry', 'Bangor', 'Craigavon'] },
  },
};
