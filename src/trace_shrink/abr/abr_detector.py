from typing import List, Union


class AbrDetector:
    """Configuration for ABR manifest detection."""

    def __init__(self):
        self._ignore_query_params: List[str] = []

    def ignore_query_params(self, params: Union[str, List[str]]) -> "AbrDetector":
        """
        Set query parameters to ignore when detecting ABR manifests.

        Args:
            params: A single parameter name or list of parameter names to ignore

        Returns:
            Self for method chaining
        """
        if isinstance(params, str):
            self._ignore_query_params = [params]
        else:
            self._ignore_query_params = list(params)
        return self

    def get_ignored_query_params(self) -> List[str]:
        """Get the list of query parameters to ignore."""
        return self._ignore_query_params.copy()
