#
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance
# with the License. A copy of the License is located at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# or in the 'license' file accompanying this file. This file is distributed on an 'AS IS' BASIS, WITHOUT WARRANTIES
# OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions
# and limitations under the License.
#
"""Abstract Graph Server Interface Module

This module defines the abstract base class for graph database servers.
It provides a common interface that can be implemented by different graph
database backends like Neptune and FalkorDB.
"""

from abc import ABC, abstractmethod
from ws_memory_mcp.models import GraphSchema, QueryLanguage


class GraphServer(ABC):
    """Abstract base class for graph database servers.

    This class defines the interface that all graph database implementations
    should follow to ensure compatibility with the memory management system.
    """

    @abstractmethod
    def close(self):
        """Close the connection to the graph database instance."""
        pass

    @abstractmethod
    def status(self) -> str:
        """Check the current status of the graph database instance.

        Returns:
            str: Current status ("Available" or "Unavailable")
        """
        pass

    @abstractmethod
    def schema(self) -> GraphSchema:
        """Retrieve the schema information from the graph database instance.

        Returns:
            GraphSchema: Complete schema information for the graph
        """
        pass

    @abstractmethod
    def query(
        self, query: str, language: QueryLanguage, parameters: dict = None
    ) -> str:
        """Execute a query against the graph database instance.

        Args:
            query (str): Query string to execute
            language (QueryLanguage): Query language to use
            parameters (dict, optional): Query parameters. Defaults to None.

        Returns:
            str: Query results

        Raises:
            ValueError: If using unsupported query language
            Exception: If query execution fails
        """
        pass
