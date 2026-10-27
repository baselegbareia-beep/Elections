# Fonts of the site, for the reports pipeline/arab_report.py renders

The site's two faces (site/src/index.html loads them from Google Fonts): IBM Plex Sans Hebrew (400, 500, 600, 700)
and Karantina (400, 700), each in its Hebrew and Latin subsets, as woff2. The report embeds them, so the PDF looks
like the site wherever it is rendered, without a network. From the @fontsource npm packages 5.3.0
(@fontsource/ibm-plex-sans-hebrew, @fontsource/karantina). Both under the SIL Open Font License 1.1 (the LICENSE
files here).
