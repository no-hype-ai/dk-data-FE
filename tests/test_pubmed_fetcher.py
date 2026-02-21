"""Tests for PubMed fetcher and validator with mocked HTTP.

Feature: 011-datasource-integration
"""

import tempfile
import textwrap
from datetime import date
from unittest.mock import patch

import pytest
import responses

from dk_data.ingestion.fetchers.pubmed import PubMedFetcher
from dk_data.ingestion.utils.validators import PubMedRecord


# ---------------------------------------------------------------------------
# Sample XML fixtures
# ---------------------------------------------------------------------------

ESEARCH_XML_2_RESULTS = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <eSearchResult>
        <Count>2</Count>
        <RetMax>500</RetMax>
        <RetStart>0</RetStart>
        <IdList>
            <Id>12345678</Id>
            <Id>87654321</Id>
        </IdList>
    </eSearchResult>
""")

ESEARCH_XML_EMPTY = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <eSearchResult>
        <Count>0</Count>
        <RetMax>500</RetMax>
        <RetStart>0</RetStart>
        <IdList/>
    </eSearchResult>
""")

EFETCH_XML_2_ARTICLES = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <PubmedArticleSet>
        <PubmedArticle>
            <MedlineCitation>
                <PMID>12345678</PMID>
                <Article>
                    <ArticleTitle>A Novel Drug Target in Oncology</ArticleTitle>
                    <Abstract>
                        <AbstractText Label="BACKGROUND">Background text here.</AbstractText>
                        <AbstractText Label="METHODS">Methods text here.</AbstractText>
                    </Abstract>
                    <AuthorList>
                        <Author>
                            <LastName>Smith</LastName>
                            <ForeName>John</ForeName>
                            <Initials>J</Initials>
                            <AffiliationInfo>
                                <Affiliation>Harvard Medical School</Affiliation>
                            </AffiliationInfo>
                        </Author>
                        <Author>
                            <LastName>Doe</LastName>
                            <ForeName>Jane</ForeName>
                            <Initials>J</Initials>
                        </Author>
                    </AuthorList>
                    <Journal>
                        <Title>The New England Journal of Medicine</Title>
                        <JournalIssue>
                            <PubDate>
                                <Year>2026</Year>
                                <Month>Feb</Month>
                                <Day>10</Day>
                            </PubDate>
                        </JournalIssue>
                    </Journal>
                    <PublicationTypeList>
                        <PublicationType>Journal Article</PublicationType>
                        <PublicationType>Clinical Trial</PublicationType>
                    </PublicationTypeList>
                    <ELocationID EIdType="doi">10.1056/NEJMoa2026372</ELocationID>
                </Article>
                <MeshHeadingList>
                    <MeshHeading>
                        <DescriptorName>Neoplasms</DescriptorName>
                    </MeshHeading>
                    <MeshHeading>
                        <DescriptorName>Drug Therapy</DescriptorName>
                    </MeshHeading>
                </MeshHeadingList>
                <KeywordList>
                    <Keyword>oncology</Keyword>
                    <Keyword>drug discovery</Keyword>
                </KeywordList>
            </MedlineCitation>
            <PubmedData>
                <ArticleIdList>
                    <ArticleId IdType="doi">10.1056/NEJMoa2026372</ArticleId>
                    <ArticleId IdType="pubmed">12345678</ArticleId>
                </ArticleIdList>
            </PubmedData>
        </PubmedArticle>
        <PubmedArticle>
            <MedlineCitation>
                <PMID>87654321</PMID>
                <Article>
                    <ArticleTitle>Cardiovascular Outcomes with New SGLT2 Inhibitor</ArticleTitle>
                    <Journal>
                        <Title>The Lancet</Title>
                        <JournalIssue>
                            <PubDate>
                                <Year>2026</Year>
                                <Month>01</Month>
                            </PubDate>
                        </JournalIssue>
                    </Journal>
                    <PublicationTypeList>
                        <PublicationType>Journal Article</PublicationType>
                    </PublicationTypeList>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
    </PubmedArticleSet>
""")

EFETCH_XML_MALFORMED = b"<notxml"


# ---------------------------------------------------------------------------
# PubMedFetcher tests
# ---------------------------------------------------------------------------

class TestPubMedFetcher:
    """Tests for PubMedFetcher class."""

    def test_fetcher_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = PubMedFetcher(data_dir=tmpdir)
            assert fetcher.SOURCE_NAME == "pubmed"
            assert "eutils" in fetcher.BASE_URL

    def test_get_latest_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = PubMedFetcher(data_dir=tmpdir)
            url = fetcher.get_latest_url()
            assert "eutils" in url
            assert "esearch" in url

    def test_init_with_api_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"NCBI_API_KEY": "test_key_123"}):
                fetcher = PubMedFetcher(data_dir=tmpdir)
                assert fetcher.api_key == "test_key_123"

    def test_init_without_api_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {}, clear=True):
                fetcher = PubMedFetcher(data_dir=tmpdir)
                assert fetcher.api_key is None

    @responses.activate
    def test_fetch_success(self):
        """Full happy-path: esearch returns 2 PMIDs, efetch returns articles."""
        # Mock esearch
        responses.add(
            responses.GET,
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            body=ESEARCH_XML_2_RESULTS.encode(),
            status=200,
            content_type="text/xml",
        )
        # Mock efetch (POST — avoids 414 URI Too Long with large ID lists)
        responses.add(
            responses.POST,
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            body=EFETCH_XML_2_ARTICLES.encode(),
            status=200,
            content_type="text/xml",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = PubMedFetcher(data_dir=tmpdir)
            result = fetcher.fetch(days_back=1)

        assert result["status"] == "success"
        assert len(result["records"]) == 2
        assert result["hash"] is not None

        # Verify first article parsed correctly
        rec0 = result["records"][0]
        assert rec0["pmid"] == "12345678"
        assert rec0["title"] == "A Novel Drug Target in Oncology"
        assert "Background text here" in rec0["abstract"]
        assert "Methods text here" in rec0["abstract"]
        assert len(rec0["authors"]) == 2
        assert rec0["authors"][0]["last_name"] == "Smith"
        assert rec0["journal"] == "The New England Journal of Medicine"
        assert rec0["publication_date"] == "2026-02-10"
        assert rec0["doi"] == "10.1056/NEJMoa2026372"
        assert "Neoplasms" in rec0["mesh_terms"]
        assert "Drug Therapy" in rec0["mesh_terms"]
        assert "Clinical Trial" in rec0["publication_types"]
        assert "oncology" in rec0["keywords"]

        # Verify second article (minimal data)
        rec1 = result["records"][1]
        assert rec1["pmid"] == "87654321"
        assert rec1["abstract"] is None
        assert rec1["doi"] is None

    @responses.activate
    def test_fetch_empty_results(self):
        """esearch returns zero results."""
        responses.add(
            responses.GET,
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            body=ESEARCH_XML_EMPTY.encode(),
            status=200,
            content_type="text/xml",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = PubMedFetcher(data_dir=tmpdir)
            result = fetcher.fetch(days_back=1)

        assert result["status"] == "success"
        assert result["records"] == []
        assert result["hash"] is None

    @responses.activate
    def test_fetch_esearch_http_error(self):
        """esearch returns a 500 error."""
        responses.add(
            responses.GET,
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            body=b"Internal Server Error",
            status=500,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = PubMedFetcher(data_dir=tmpdir)
            result = fetcher.fetch(days_back=1)

        assert result["status"] == "failed"
        assert result["error"]

    @responses.activate
    def test_fetch_efetch_http_error(self):
        """esearch succeeds but efetch returns a 500 error."""
        responses.add(
            responses.GET,
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            body=ESEARCH_XML_2_RESULTS.encode(),
            status=200,
            content_type="text/xml",
        )
        responses.add(
            responses.POST,
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            body=b"Internal Server Error",
            status=500,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = PubMedFetcher(data_dir=tmpdir)
            result = fetcher.fetch(days_back=1)

        assert result["status"] == "failed"
        assert result["error"]

    @responses.activate
    def test_fetch_efetch_malformed_xml(self):
        """efetch returns unparseable XML -- should fail gracefully."""
        responses.add(
            responses.GET,
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            body=ESEARCH_XML_2_RESULTS.encode(),
            status=200,
            content_type="text/xml",
        )
        responses.add(
            responses.POST,
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            body=EFETCH_XML_MALFORMED,
            status=200,
            content_type="text/xml",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = PubMedFetcher(data_dir=tmpdir)
            result = fetcher.fetch(days_back=1)

        # Should succeed with 0 records since XML was unparseable
        assert result["status"] == "success"
        assert len(result["records"]) == 0

    def test_common_params_without_api_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {}, clear=True):
                fetcher = PubMedFetcher(data_dir=tmpdir)
                params = fetcher._common_params()
                assert params == {"db": "pubmed"}
                assert "api_key" not in params

    def test_common_params_with_api_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"NCBI_API_KEY": "abc123"}):
                fetcher = PubMedFetcher(data_dir=tmpdir)
                params = fetcher._common_params()
                assert params["api_key"] == "abc123"

    def test_month_to_num(self):
        assert PubMedFetcher._month_to_num("Jan") == 1
        assert PubMedFetcher._month_to_num("february") == 2
        assert PubMedFetcher._month_to_num("12") == 12
        assert PubMedFetcher._month_to_num("03") == 3
        assert PubMedFetcher._month_to_num(None) is None
        assert PubMedFetcher._month_to_num("invalid") is None

    @responses.activate
    def test_esearch_pagination(self):
        """esearch with more results than retmax triggers pagination."""
        # First page: count=3, returns 2
        page1 = textwrap.dedent("""\
            <?xml version="1.0"?>
            <eSearchResult>
                <Count>3</Count><RetMax>2</RetMax><RetStart>0</RetStart>
                <IdList><Id>111</Id><Id>222</Id></IdList>
            </eSearchResult>
        """)
        # Second page: returns 1
        page2 = textwrap.dedent("""\
            <?xml version="1.0"?>
            <eSearchResult>
                <Count>3</Count><RetMax>2</RetMax><RetStart>2</RetStart>
                <IdList><Id>333</Id></IdList>
            </eSearchResult>
        """)

        responses.add(
            responses.GET,
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            body=page1.encode(), status=200, content_type="text/xml",
        )
        responses.add(
            responses.GET,
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            body=page2.encode(), status=200, content_type="text/xml",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = PubMedFetcher(data_dir=tmpdir)
            pmids = fetcher._esearch("test query", days_back=7, retmax=2)

        assert pmids == ["111", "222", "333"]


# ---------------------------------------------------------------------------
# PubMedRecord validator tests
# ---------------------------------------------------------------------------

class TestPubMedRecord:
    """Tests for the PubMedRecord Pydantic model."""

    def test_valid_record(self):
        record = PubMedRecord(
            pmid="12345678",
            title="Test Article Title",
            abstract="This is a test abstract.",
            authors=[{"last_name": "Smith", "fore_name": "John"}],
            journal="Nature",
            publication_date=date(2026, 1, 15),
            mesh_terms=["Neoplasms", "Drug Therapy"],
            doi="10.1038/s41586-026-00001-0",
            publication_types=["Journal Article"],
            keywords=["cancer", "targeted therapy"],
        )
        assert record.pmid == "12345678"
        assert record.title == "Test Article Title"
        assert record.journal == "Nature"
        assert record.doi == "10.1038/s41586-026-00001-0"
        assert len(record.mesh_terms) == 2
        assert len(record.keywords) == 2

    def test_minimal_record(self):
        record = PubMedRecord(pmid="99999999", title="Minimal")
        assert record.pmid == "99999999"
        assert record.abstract is None
        assert record.authors is None
        assert record.journal is None
        assert record.publication_date is None
        assert record.mesh_terms is None
        assert record.doi is None

    def test_invalid_pmid_non_numeric(self):
        with pytest.raises(ValueError, match="PMID must be numeric"):
            PubMedRecord(pmid="abc", title="Test")

    def test_invalid_pmid_empty(self):
        with pytest.raises(ValueError):
            PubMedRecord(pmid="", title="Test")

    def test_invalid_doi(self):
        with pytest.raises(ValueError, match="DOI must start with 10."):
            PubMedRecord(pmid="12345678", title="Test", doi="not-a-doi")

    def test_valid_doi_none(self):
        record = PubMedRecord(pmid="12345678", title="Test", doi=None)
        assert record.doi is None

    def test_title_required(self):
        with pytest.raises(ValueError):
            PubMedRecord(pmid="12345678", title="")

    def test_pmid_whitespace_stripped(self):
        record = PubMedRecord(pmid="  12345678  ", title="Test")
        assert record.pmid == "12345678"

    def test_doi_whitespace_stripped(self):
        record = PubMedRecord(
            pmid="12345678", title="Test", doi="  10.1234/test  "
        )
        assert record.doi == "10.1234/test"


# ---------------------------------------------------------------------------
# XML parsing unit tests
# ---------------------------------------------------------------------------

class TestXMLParsing:
    """Test low-level XML parsing helpers."""

    def test_parse_efetch_xml_valid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = PubMedFetcher(data_dir=tmpdir)
            records = fetcher._parse_efetch_xml(EFETCH_XML_2_ARTICLES.encode())
            assert len(records) == 2

    def test_parse_efetch_xml_malformed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = PubMedFetcher(data_dir=tmpdir)
            records = fetcher._parse_efetch_xml(EFETCH_XML_MALFORMED)
            assert records == []

    def test_parse_pub_date_year_only(self):
        """Article with only <Year> should yield YYYY-01-01."""
        xml = textwrap.dedent("""\
            <?xml version="1.0"?>
            <PubmedArticleSet>
                <PubmedArticle>
                    <MedlineCitation>
                        <PMID>99999999</PMID>
                        <Article>
                            <ArticleTitle>Year Only</ArticleTitle>
                            <Journal>
                                <Title>J Test</Title>
                                <JournalIssue>
                                    <PubDate><Year>2025</Year></PubDate>
                                </JournalIssue>
                            </Journal>
                        </Article>
                    </MedlineCitation>
                </PubmedArticle>
            </PubmedArticleSet>
        """)
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = PubMedFetcher(data_dir=tmpdir)
            records = fetcher._parse_efetch_xml(xml.encode())
            assert len(records) == 1
            assert records[0]["publication_date"] == "2025-01-01"

    def test_parse_authors(self):
        """Check that authors are parsed with all fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = PubMedFetcher(data_dir=tmpdir)
            records = fetcher._parse_efetch_xml(EFETCH_XML_2_ARTICLES.encode())
            authors = records[0]["authors"]
            assert len(authors) == 2
            assert authors[0]["last_name"] == "Smith"
            assert authors[0]["fore_name"] == "John"
            assert authors[0]["initials"] == "J"
            assert authors[0]["affiliation"] == "Harvard Medical School"
            assert authors[1]["last_name"] == "Doe"

    def test_parse_mesh_terms(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = PubMedFetcher(data_dir=tmpdir)
            records = fetcher._parse_efetch_xml(EFETCH_XML_2_ARTICLES.encode())
            assert "Neoplasms" in records[0]["mesh_terms"]
            assert "Drug Therapy" in records[0]["mesh_terms"]

    def test_parse_doi_from_elocationid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = PubMedFetcher(data_dir=tmpdir)
            records = fetcher._parse_efetch_xml(EFETCH_XML_2_ARTICLES.encode())
            assert records[0]["doi"] == "10.1056/NEJMoa2026372"
