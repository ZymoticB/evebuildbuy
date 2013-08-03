angular.module('evetools', ['ui.bootstrap', 'uiSlider', 'ngResource']).config(function($routeProvider) {
	$routeProvider.
		when('/', {controller:MainCtrl, templateUrl:'main.html'}).
		when('/item', {controller:ItemCtrl, templateUrl:'item.html'}).
		when('/contact', {controller:ContactCtrl, templateUrl:'contact.html'}).
		otherwise({redirectTo:'/'});
	});

var Item = $resource('/item/:item_name/',
				{item_name:'@item', me:2});


function ContactCtrl($scope){
}

function MainCtrl($scope){
}

function ItemCtrl($scope) {
	$scope.itemME = 0;
	$scope.partME = 0;
}
